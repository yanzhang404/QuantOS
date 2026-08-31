from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from quantos_cli import main
from quantos_radar.collector import PublicRadarCollector
from quantos_radar.errors import RadarError, RadarValidationError
from quantos_radar.models import MarketRadarInput
from quantos_radar.refresh import RadarRefresher, RefreshHealth
from quantos_radar.scoring import build_snapshot
from quantos_radar.store import publish_snapshot

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "radar" / "sample-input.v1.json"
SAMPLE_SNAPSHOT = ROOT / "examples" / "radar" / "sample-snapshot.v1.json"
AS_OF = datetime(2026, 8, 12, 2, 30, tzinfo=UTC)


def sample_payload() -> dict[str, object]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def public_client(
    *, fail: bool = False, rows: list[dict[str, object]] | None = None
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(503, request=request)
        assert request.method == "GET"
        assert request.url.path == "/api/qt/clist/get"
        assert request.url.params["pz"] == "100"
        assert "f100" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "diff": [
                        *(
                            rows
                            if rows is not None
                            else [
                                mover("600001", 1, "液冷一号", "6.8", "液冷"),
                                mover("000001", 0, "液冷二号", "5.2", "液冷"),
                                mover("300001", 0, "下跌样本", "-7.0", "其他"),
                                mover("600002", 1, "无标签样本", "8.0", "-"),
                            ]
                        )
                    ]
                }
            },
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def mover(code: str, market: int, name: str, change: str, industry: str) -> dict[str, object]:
    return {
        "f2": "26.8",
        "f3": change,
        "f8": "9.4",
        "f10": "3.1",
        "f12": code,
        "f13": market,
        "f14": name,
        "f100": industry,
    }


def test_builds_reproducible_stock_theme_heat_snapshot() -> None:
    radar = MarketRadarInput.from_dict(sample_payload())

    first = build_snapshot(radar)
    second = build_snapshot(radar)

    assert first == second
    assert first == json.loads(SAMPLE_SNAPSHOT.read_text(encoding="utf-8"))
    assert first["methodology_version"] == "quantos-market-radar-v1.0.0"
    assert first["summary"]["hottest_theme"] == "液冷"
    assert first["stocks"][0]["symbol"] == "000001.SZ"
    assert first["stocks"][0]["data_coverage"] == 1.0
    assert first["themes"][0]["observed_breadth"] == 2


def test_computes_thirty_and_sixty_minute_acceleration() -> None:
    baseline_payload = sample_payload()
    baseline_payload["as_of"] = "2026-08-12T02:00:00Z"
    for stock in baseline_payload["stocks"]:  # type: ignore[index]
        stock["observed_at"] = "2026-08-12T01:59:00Z"
    baseline = build_snapshot(MarketRadarInput.from_dict(baseline_payload))

    current_payload = sample_payload()
    current_payload["stocks"][0]["change_pct"] = 8.0  # type: ignore[index]
    current = build_snapshot(MarketRadarInput.from_dict(current_payload), [baseline])

    leader = next(stock for stock in current["stocks"] if stock["symbol"] == "000001.SZ")
    liquid_cooling = next(theme for theme in current["themes"] if theme["name"] == "液冷")
    assert leader["acceleration_30m"] > 0
    assert leader["acceleration_60m"] is None
    assert liquid_cooling["acceleration_30m"] > 0
    assert current["summary"]["fastest_rising_theme"] == "液冷"


def test_collector_normalizes_only_positive_industry_tagged_a_share_movers() -> None:
    with public_client() as client:
        radar = PublicRadarCollector(client).collect(
            as_of=AS_OF, observed_at=AS_OF + timedelta(minutes=9)
        )

    assert radar.status == "partial"
    assert radar.provider == "Eastmoney A-share snapshot"
    assert [stock.symbol for stock in radar.stocks] == ["600001.SH", "000001.SZ"]
    assert radar.stocks[0].change_pct == pytest.approx(6.8)
    assert radar.stocks[0].relative_volume == pytest.approx(3.1)
    assert radar.stocks[0].turnover_pct == pytest.approx(9.4)
    assert radar.stocks[0].themes == ("液冷",)
    assert radar.stocks[0].observed_at == AS_OF + timedelta(minutes=9)
    assert radar.stocks[0].source_url.startswith("https://push2.eastmoney.com/")

    with public_client(rows=[]) as client, pytest.raises(RadarError, match="no valid movers"):
        PublicRadarCollector(client).collect(as_of=AS_OF)


def test_rejects_unsafe_unknown_or_false_complete_inputs() -> None:
    unsafe = sample_payload()
    unsafe["stocks"][0]["source_url"] = "http://localhost/data"  # type: ignore[index]
    with pytest.raises(RadarValidationError, match="HTTPS URL"):
        MarketRadarInput.from_dict(unsafe)

    unknown = sample_payload()
    unknown["command"] = "place-order"
    with pytest.raises(RadarValidationError, match="unknown fields"):
        MarketRadarInput.from_dict(unknown)

    incomplete = sample_payload()
    incomplete["status"] = "complete"
    incomplete["stocks"][0]["relative_volume"] = None  # type: ignore[index]
    with pytest.raises(RadarValidationError, match="every heat component"):
        MarketRadarInput.from_dict(incomplete)


def test_publishes_immutable_bucket_and_latest(tmp_path: Path) -> None:
    snapshot = build_snapshot(MarketRadarInput.from_dict(sample_payload()))

    history, latest = publish_snapshot(snapshot, tmp_path)
    repeated_history, repeated_latest = publish_snapshot(snapshot, tmp_path)

    assert history.relative_to(tmp_path).as_posix() == "snapshots/2026-08-12/0230.json"
    assert history.read_bytes() == latest.read_bytes()
    assert (repeated_history, repeated_latest) == (history, latest)


def test_rejects_conflicting_bucket_and_backward_latest(tmp_path: Path) -> None:
    current = build_snapshot(MarketRadarInput.from_dict(sample_payload()))
    _, latest = publish_snapshot(current, tmp_path)
    previous_latest = latest.read_bytes()

    conflicting_payload = sample_payload()
    conflicting_payload["stocks"][0]["change_pct"] = 8.1  # type: ignore[index]
    conflicting = build_snapshot(MarketRadarInput.from_dict(conflicting_payload))
    with pytest.raises(RadarValidationError, match="different content"):
        publish_snapshot(conflicting, tmp_path)

    older_payload = sample_payload()
    older_payload["as_of"] = "2026-08-12T02:20:00Z"
    for stock in older_payload["stocks"]:  # type: ignore[index]
        stock["observed_at"] = "2026-08-12T02:19:00Z"
    older = build_snapshot(MarketRadarInput.from_dict(older_payload))
    with pytest.raises(RadarValidationError, match="cannot move backward"):
        publish_snapshot(older, tmp_path)

    assert latest.read_bytes() == previous_latest
    assert not (tmp_path / "snapshots" / "2026-08-12" / "0220.json").exists()


def test_cli_builds_and_publishes_sample(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "radar"

    assert (
        main(
            [
                "radar",
                "build",
                "--input",
                str(SAMPLE),
                "--output-root",
                str(output),
            ]
        )
        == 0
    )

    result = json.loads(capsys.readouterr().out)
    assert result["stock_count"] == 6
    assert result["theme_count"] == 4
    assert Path(result["latest"]).is_file()


def test_refresh_reuses_bucket_and_preserves_latest_on_failure(tmp_path: Path) -> None:
    refresher = RadarRefresher(
        input_root=tmp_path / "inputs",
        output_root=tmp_path / "radar",
        client_factory=public_client,
        now=lambda: AS_OF,
    )
    first = refresher.run(as_of=AS_OF + timedelta(minutes=4))
    previous = Path(first["latest"]).read_bytes()

    def forbidden_client() -> httpx.Client:
        raise AssertionError("same bucket must reuse its pinned input")

    refresher.client_factory = forbidden_client
    second = refresher.run(as_of=AS_OF + timedelta(minutes=8))
    assert second["input"] == first["input"]

    failed = RadarRefresher(
        input_root=tmp_path / "inputs",
        output_root=tmp_path / "radar",
        client_factory=lambda: public_client(fail=True),
        now=lambda: AS_OF + timedelta(minutes=10),
    )
    with pytest.raises(RadarError, match="request failed"):
        failed.run(as_of=AS_OF + timedelta(minutes=10))

    assert Path(first["latest"]).read_bytes() == previous
    health = RefreshHealth.from_dict(
        json.loads((tmp_path / "radar" / "refresh-health.json").read_text(encoding="utf-8"))
    )
    assert health.state == "failed"
    assert health.last_success_bucket == "2026-08-12T02:30Z"
    assert health.consecutive_failures == 1

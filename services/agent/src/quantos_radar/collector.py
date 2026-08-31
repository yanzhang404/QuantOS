"""Bounded public collector for current Eastmoney A-share snapshots."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import RadarError, RadarValidationError
from .models import MarketRadarInput, RadarStockInput

EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/clist/get"
USER_AGENT = "QuantOS-Research/0.5 public-read-only market-radar"
MAX_RESPONSE_BYTES = 4 << 20
MAX_STOCKS = 100
MARKET_FILTER = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
FIELDS = "f2,f3,f5,f6,f8,f10,f12,f13,f14,f100,f127"


class PublicRadarCollector:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def collect(self, *, as_of: datetime, observed_at: datetime | None = None) -> MarketRadarInput:
        if as_of.tzinfo is None or (observed_at is not None and observed_at.tzinfo is None):
            raise RadarValidationError("radar timestamps must include a timezone")
        as_of = as_of.astimezone(UTC)
        observed_at = (observed_at or as_of).astimezone(UTC)
        payload = self._json()
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("diff") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) > MAX_STOCKS:
            raise RadarError("Eastmoney A-share snapshot is invalid")
        stocks: list[RadarStockInput] = []
        for row in rows:
            stock = self._stock(row, observed_at)
            if stock is not None:
                stocks.append(stock)
        unique: dict[str, RadarStockInput] = {}
        for stock in stocks:
            if stock.symbol in unique:
                raise RadarError("Eastmoney A-share snapshot contains duplicate stocks")
            unique[stock.symbol] = stock
        if not unique:
            raise RadarError("Eastmoney A-share snapshot contains no valid movers")
        radar = MarketRadarInput(
            market="CN",
            as_of=as_of,
            status="partial",
            provider="Eastmoney A-share snapshot",
            stocks=tuple(unique.values()),
        )
        return MarketRadarInput.from_dict(radar.to_dict())

    def _json(self) -> Any:
        _allowed_url(EASTMONEY_URL)
        params = {
            "pn": 1,
            "pz": MAX_STOCKS,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": MARKET_FILTER,
            "fields": FIELDS,
        }
        try:
            response = self.client.get(
                EASTMONEY_URL,
                params=params,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RadarError("public radar collector request failed") from exc
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise RadarError("public radar collector response is too large")
        _allowed_url(str(response.url).split("?", 1)[0])
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise RadarError("public radar collector returned invalid JSON") from exc

    def _stock(self, row: Any, as_of: datetime) -> RadarStockInput | None:
        if not isinstance(row, dict):
            return None
        try:
            change_pct = _number(row.get("f3"), "change")
            if change_pct <= 0:
                return None
            symbol = _symbol(row.get("f12"), row.get("f13"))
            name = _plain(row.get("f14"), 80)
            last_price = _positive_number(row.get("f2"), "last price")
            relative_volume = _optional_number(row.get("f10"), "relative volume", 0, 100)
            turnover_pct = _optional_number(row.get("f8"), "turnover", 0, 100)
            industry = _industry(row)
        except RadarError:
            return None
        signals = [f"涨幅 {change_pct:.1f}%"]
        if relative_volume is not None and relative_volume >= 2:
            signals.append(f"量比 {relative_volume:.1f} 倍")
        if turnover_pct is not None and turnover_pct >= 5:
            signals.append(f"换手率 {turnover_pct:.1f}%")
        return RadarStockInput(
            symbol=symbol,
            name=name,
            last_price=last_price,
            change_pct=change_pct,
            relative_volume=relative_volume,
            turnover_pct=turnover_pct,
            change_30m_pct=None,
            new_high_20d=None,
            themes=(industry,),
            signals=tuple(signals[:8]),
            source_url=EASTMONEY_URL,
            observed_at=as_of,
            catalyst=None,
        )


def build_public_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15), follow_redirects=False)


def _allowed_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or (parsed.hostname, parsed.path) != ("push2.eastmoney.com", "/api/qt/clist/get")
    ):
        raise RadarValidationError("radar collector URL is not allow-listed")


def _symbol(code_value: Any, market_value: Any) -> str:
    code = str(code_value or "").strip()
    if not re.fullmatch(r"[0-9]{6}", code):
        raise RadarError("Eastmoney stock code is invalid")
    try:
        market = int(market_value)
    except (TypeError, ValueError) as exc:
        raise RadarError("Eastmoney stock market is invalid") from exc
    if code.startswith(("4", "8")):
        suffix = "BJ"
    elif market == 1:
        suffix = "SH"
    elif market == 0:
        suffix = "SZ"
    else:
        raise RadarError("Eastmoney stock market is unsupported")
    return f"{code}.{suffix}"


def _industry(row: dict[str, Any]) -> str:
    for key in ("f100", "f127"):
        value = row.get(key)
        if isinstance(value, str) and value.strip() not in {"", "-"}:
            return _plain(value, 40)
    raise RadarError("Eastmoney industry label is unavailable")


def _number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RadarError(f"Eastmoney {field} is invalid") from exc
    if not math.isfinite(parsed):
        raise RadarError(f"Eastmoney {field} is invalid")
    return parsed


def _positive_number(value: Any, field: str) -> float:
    parsed = _number(value, field)
    if parsed <= 0:
        raise RadarError(f"Eastmoney {field} is invalid")
    return parsed


def _optional_number(value: Any, field: str, minimum: float, maximum: float) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    parsed = _number(value, field)
    if not minimum <= parsed <= maximum:
        raise RadarError(f"Eastmoney {field} is invalid")
    return parsed


def _plain(value: Any, maximum: int) -> str:
    if not isinstance(value, str):
        raise RadarError("Eastmoney text field is invalid")
    text = " ".join(value.split())
    if not text or len(text) > maximum or any(character in text for character in ("`", "<", ">")):
        raise RadarError("Eastmoney text field is invalid")
    return text

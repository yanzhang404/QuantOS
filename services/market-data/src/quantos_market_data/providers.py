"""Read-only providers for normalized A-share quote snapshots."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import StockQuote


class MarketSnapshotProvider(Protocol):
    name: str

    def fetch_quotes(self) -> Sequence[StockQuote]: ...


class JsonSnapshotProvider:
    """Deterministic provider for recorded snapshots and offline replay."""

    name = "json-snapshot"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch_quotes(self) -> list[StockQuote]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rows = payload["quotes"] if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("snapshot must be a JSON list or an object with quotes")
        return [StockQuote.from_dict(row) for row in rows]


def load_theme_map(path: str | Path | None) -> dict[str, tuple[str, ...]]:
    """Load either {symbol: [themes]} or {theme: [symbols]} JSON."""
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("theme map must be a JSON object")
    result: dict[str, set[str]] = {}
    symbol_keyed = all(str(key).isdigit() for key in payload)
    if symbol_keyed:
        for symbol, themes in payload.items():
            if not isinstance(themes, list):
                raise ValueError("each symbol must map to a list of themes")
            result.setdefault(str(symbol), set()).update(map(str, themes))
    else:
        for theme, symbols in payload.items():
            if not isinstance(symbols, list):
                raise ValueError("each theme must map to a list of symbols")
            for symbol in symbols:
                result.setdefault(str(symbol), set()).add(str(theme))
    return {symbol: tuple(sorted(themes)) for symbol, themes in result.items()}


class EastmoneyAShareProvider:
    """Fetch a point-in-time A-share universe from Eastmoney's public quote API.

    The adapter contains all vendor-specific fields. No Eastmoney response model
    crosses this boundary. Calls are read-only and require no credentials.
    """

    name = "eastmoney-a-share"
    endpoints = (
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
        "https://20.push2.eastmoney.com/api/qt/clist/get",
        "https://40.push2.eastmoney.com/api/qt/clist/get",
    )
    fields = "f2,f3,f5,f6,f7,f8,f10,f12,f13,f14,f15,f16,f17,f18,f22"
    universe = "m:0+t:6,m:0+t:80,m:0+t:81+s:2048,m:1+t:2,m:1+t:23"

    def __init__(
        self,
        theme_map: Mapping[str, tuple[str, ...]] | None = None,
        page_size: int = 100,
        timeout: float = 15.0,
        retries: int = 4,
        page_delay: float = 0.1,
    ) -> None:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and Eastmoney's limit of 100")
        if page_delay < 0:
            raise ValueError("page_delay must be non-negative")
        self.theme_map = dict(theme_map or {})
        self.page_size = page_size
        self.timeout = timeout
        self.retries = retries
        self.page_delay = page_delay

    def fetch_quotes(self) -> list[StockQuote]:
        observed_at = datetime.now(timezone.utc)
        result: dict[str, StockQuote] = {}
        page = 1
        total = None
        while total is None or (page - 1) * self.page_size < total:
            payload = self._fetch_page(page)
            data = payload.get("data") or {}
            rows = data.get("diff") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            if not rows:
                break
            total = int(data.get("total") or len(rows))
            for row in rows:
                quote = self._normalize(row, observed_at)
                if quote is not None:
                    result[quote.symbol] = quote
            if len(rows) < self.page_size:
                break
            page += 1
            if self.page_delay:
                time.sleep(self.page_delay)
        if not result:
            raise RuntimeError("Eastmoney returned no valid A-share quotes")
        return sorted(result.values(), key=lambda item: (item.exchange, item.symbol))

    def _fetch_page(self, page: int) -> dict[str, Any]:
        params = {
            "pn": page,
            "pz": self.page_size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": self.universe,
            "fields": self.fields,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            endpoint = self.endpoints[attempt % len(self.endpoints)]
            request = Request(
                f"{endpoint}?{urlencode(params)}",
                headers={
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/126.0 Safari/537.36 "
                        "QuantOS-MarketRadar/0.1"
                    ),
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:  # boundary converts transport failures
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"failed to fetch Eastmoney page {page}: {last_error}")

    def _normalize(
        self, row: Mapping[str, Any], observed_at: datetime
    ) -> StockQuote | None:
        symbol = str(row.get("f12") or "")
        if len(symbol) != 6 or not symbol.isdigit():
            return None
        try:
            price = self._number(row.get("f2"))
            prev_close = self._number(row.get("f18"))
            if price <= 0 or prev_close <= 0:
                return None
            return StockQuote(
                symbol=symbol,
                name=str(row.get("f14") or symbol),
                exchange=self._exchange(symbol, row.get("f13")),
                timestamp=observed_at,
                price=price,
                prev_close=prev_close,
                change_pct=self._number(row.get("f3")),
                volume=self._number(row.get("f5")),
                amount=self._number(row.get("f6")),
                turnover_rate=self._number(row.get("f8")),
                volume_ratio=self._number(row.get("f10")),
                amplitude_pct=self._number(row.get("f7")),
                change_5m_pct=self._number(row.get("f22")),
                themes=self.theme_map.get(symbol, ()),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _number(value: Any) -> float:
        if value in (None, "", "-"):
            return 0.0
        return float(value)

    @staticmethod
    def _exchange(symbol: str, market: Any) -> str:
        if symbol.startswith(("4", "8", "92")):
            return "XBSE"
        if str(market) == "1" or symbol.startswith(("5", "6", "9")):
            return "XSHG"
        return "XSHE"

"""Notification boundaries for market-radar summaries."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol
from urllib.request import Request, urlopen

from .us_models import USMarketHeatReport
from .options_models import USOptionsRadarReport


class Notifier(Protocol):
    async def send(self, message: str) -> None: ...


class ConsoleNotifier:
    async def send(self, message: str) -> None:
        print(message, flush=True)


class CompositeNotifier:
    def __init__(self, notifiers: list[Notifier], strict: bool = False) -> None:
        self.notifiers = notifiers
        self.strict = strict

    async def send(self, message: str) -> None:
        results = await asyncio.gather(
            *(item.send(message) for item in self.notifiers),
            return_exceptions=not self.strict,
        )
        if not self.strict:
            for result in results:
                if isinstance(result, Exception):
                    logging.error("market-radar notification failed: %s", result)


class WebhookNotifier:
    def __init__(self, url: str, format_name: str = "slack", timeout: float = 10.0) -> None:
        if format_name not in {"slack", "wecom", "generic"}:
            raise ValueError("webhook format must be slack, wecom, or generic")
        self.url = url
        self.format_name = format_name
        self.timeout = timeout

    async def send(self, message: str) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: str) -> None:
        if self.format_name == "wecom":
            payload = {"msgtype": "text", "text": {"content": message}}
        else:
            payload = {"text": message}
        request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"webhook returned HTTP {response.status}")


def format_us_heat_report(report: USMarketHeatReport) -> str:
    local_time = report.generated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        f"QuantOS 美股热度 | {local_time}",
        f"数据源 {report.source} | 跟踪 {report.tracked_symbols} 只 | Top {len(report.candidates)}",
    ]
    for rank, item in enumerate(report.candidates, start=1):
        arrow = "↑" if item.direction == "up" else "↓" if item.direction == "down" else "→"
        lines.append(
            f"{rank}. {item.symbol} {arrow} 热度 {item.heat_score:.1f} | "
            f"5m {item.change_5m_pct:+.2f}% | 量速 {item.volume_ratio_5m:.2f}x | "
            f"5m成交 ${item.dollar_volume_5m / 1_000_000:.1f}M"
        )
    lines.append("仅为行情筛选；期权价差、IV、Greeks 和可交易性尚未评估。")
    return "\n".join(lines)


def format_us_options_report(report: USOptionsRadarReport) -> str:
    local_time = report.generated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        f"QuantOS 美股期权候选 | {local_time}",
        f"股票 {report.equity_source} | 期权 {report.options_source}",
    ]
    for rank, underlying in enumerate(report.underlyings, start=1):
        arrow = "↑" if underlying.direction == "up" else "↓" if underlying.direction == "down" else "→"
        lines.append(
            f"{rank}. {underlying.symbol} {arrow} 股票热度 {underlying.heat_score:.1f} | "
            f"期权状态 {underlying.status}"
        )
        for contract in underlying.contracts:
            flags = ",".join(contract.risk_flags) if contract.risk_flags else "none"
            lines.append(
                f"   {contract.contract_symbol} | 可交易性 {contract.score:.1f} | "
                f"中间价 ${contract.mid_price:.2f} | 价差 {contract.spread_pct:.1f}% | "
                f"风险 {flags}"
            )
        if underlying.error:
            lines.append(f"   数据错误：{underlying.error}")
    lines.append("仅为研究筛选，不是买卖或合约推荐；下单前须人工复核实时 NBBO、IV 与风险。")
    return "\n".join(lines)

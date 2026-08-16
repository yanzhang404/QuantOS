"""Alpaca live and recorded one-minute US equity bar providers."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator, Protocol

from .us_models import USEquityBar


class USBarStreamProvider(Protocol):
    name: str

    def stream_bars(self) -> AsyncIterator[USEquityBar]: ...


class AlpacaStreamRejected(RuntimeError):
    """The server rejected credentials, entitlements, or a subscription."""


class JsonLineBarStream:
    """Replay Alpaca-shaped or normalized bars from a JSON Lines file."""

    name = "jsonl-replay"

    def __init__(self, path: str | Path, delay_seconds: float = 0.0) -> None:
        self.path = Path(path)
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        self.delay_seconds = delay_seconds

    async def stream_bars(self) -> AsyncIterator[USEquityBar]:
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            payload = json.loads(line)
            messages = payload if isinstance(payload, list) else [payload]
            for message in messages:
                if message.get("T") not in (None, "b", "u"):
                    continue
                try:
                    yield USEquityBar.from_dict(message)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid replay bar at line {line_number}: {exc}") from exc
                if self.delay_seconds:
                    await asyncio.sleep(self.delay_seconds)


class AlpacaBarStream:
    """Stream all entitled US equity minute bars from Alpaca."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        feed: str = "sip",
        max_reconnect_delay: float = 60.0,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required")
        if feed not in {"sip", "iex", "delayed_sip"}:
            raise ValueError("feed must be sip, iex, or delayed_sip")
        self.api_key = api_key
        self.api_secret = api_secret
        self.feed = feed
        self.max_reconnect_delay = max_reconnect_delay
        self.name = f"alpaca-{feed}"

    async def stream_bars(self) -> AsyncIterator[USEquityBar]:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("install quantos-market-data with its live dependencies") from exc

        reconnect_attempt = 0
        while True:
            try:
                async for bar in self._stream_once(websockets):
                    reconnect_attempt = 0
                    yield bar
                raise ConnectionError("Alpaca stream closed without an error")
            except AlpacaStreamRejected:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = min(self.max_reconnect_delay, 2 ** reconnect_attempt)
                logging.warning("Alpaca stream disconnected; reconnecting in %.1fs: %s", delay, exc)
                reconnect_attempt += 1
                await asyncio.sleep(delay)

    async def _stream_once(self, websockets) -> AsyncIterator[USEquityBar]:
        url = f"wss://stream.data.alpaca.markets/v2/{self.feed}"
        async with websockets.connect(
            url, ping_interval=20, ping_timeout=20, max_queue=4096
        ) as connection:
            await self._expect_connected(connection)
            await connection.send(json.dumps({
                "action": "auth", "key": self.api_key, "secret": self.api_secret,
            }))
            await self._expect_authenticated(connection)
            await connection.send(json.dumps({"action": "subscribe", "bars": ["*"]}))
            async for raw in connection:
                messages = json.loads(raw)
                if not isinstance(messages, list):
                    messages = [messages]
                for message in messages:
                    if message.get("T") == "error":
                        raise AlpacaStreamRejected(
                            f"Alpaca stream error {message.get('code')}: {message.get('msg')}"
                        )
                    if message.get("T") in {"b", "u"}:
                        yield USEquityBar.from_dict(message)

    @staticmethod
    async def _receive_messages(connection) -> list[dict]:
        payload = json.loads(await connection.recv())
        return payload if isinstance(payload, list) else [payload]

    async def _expect_connected(self, connection) -> None:
        messages = await self._receive_messages(connection)
        if not any(item.get("T") == "success" and item.get("msg") == "connected"
                   for item in messages):
            raise RuntimeError(f"unexpected Alpaca connection response: {messages}")

    async def _expect_authenticated(self, connection) -> None:
        messages = await self._receive_messages(connection)
        for item in messages:
            if item.get("T") == "error":
                raise AlpacaStreamRejected(
                    f"Alpaca authentication failed {item.get('code')}: {item.get('msg')}"
                )
        if not any(item.get("T") == "success" and item.get("msg") == "authenticated"
                   for item in messages):
            raise RuntimeError(f"unexpected Alpaca authentication response: {messages}")

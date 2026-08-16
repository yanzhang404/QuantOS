import asyncio
import json
from unittest.mock import patch
import unittest

from quantos_market_data.alpaca import AlpacaBarStream, AlpacaStreamRejected
from quantos_market_data.notifiers import WebhookNotifier


class FakeConnection:
    def __init__(self, responses):
        self.responses = iter(responses)

    async def recv(self):
        return next(self.responses)


class AlpacaHandshakeTests(unittest.TestCase):
    def test_accepts_expected_connection_and_authentication(self):
        connection = FakeConnection([
            json.dumps([{"T": "success", "msg": "connected"}]),
            json.dumps([{"T": "success", "msg": "authenticated"}]),
        ])
        provider = AlpacaBarStream("key", "secret", "iex")

        async def verify():
            await provider._expect_connected(connection)
            await provider._expect_authenticated(connection)

        asyncio.run(verify())

    def test_authentication_rejection_fails_loudly(self):
        connection = FakeConnection([
            json.dumps([{"T": "error", "code": 401, "msg": "auth failed"}])
        ])
        provider = AlpacaBarStream("key", "secret")
        with self.assertRaisesRegex(AlpacaStreamRejected, "401"):
            asyncio.run(provider._expect_authenticated(connection))


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class WebhookTests(unittest.TestCase):
    def test_wecom_payload_shape(self):
        requests = []

        def open_request(request, timeout):
            requests.append(request)
            return FakeResponse()

        notifier = WebhookNotifier("https://example.invalid/hook", "wecom")
        with patch("quantos_market_data.notifiers.urlopen", open_request):
            notifier._send_sync("hello")
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload, {"msgtype": "text", "text": {"content": "hello"}})


if __name__ == "__main__":
    unittest.main()

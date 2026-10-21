import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from procurement_agent.cli import main
from procurement_agent.openrouter import OpenRouterClient, OpenRouterError


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenRouterClient("test-secret", "test/model")

    @patch("procurement_agent.openrouter.urlopen")
    def test_request_and_completion(self, send):
        send.return_value.__enter__.return_value = io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        }).encode())
        self.assertEqual(self.client.complete([{"role": "user", "content": "hello"}]), "ok")
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(request.data)["model"], "test/model")
        self.assertNotIn("test-secret", repr(self.client))

    @patch("procurement_agent.openrouter.urlopen")
    def test_http_error_does_not_expose_response_body(self, send):
        send.side_effect = HTTPError("url", 401, "test-secret", {}, None)
        with self.assertRaisesRegex(OpenRouterError, "HTTP 401") as error:
            self.client.complete([])
        self.assertNotIn("test-secret", str(error.exception))

    @patch("procurement_agent.openrouter.urlopen")
    def test_rejects_truncated_completion(self, send):
        send.return_value.__enter__.return_value = io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "length", "message": {"content": "partial"}}],
        }).encode())
        with self.assertRaisesRegex(OpenRouterError, "did not finish"):
            self.client.complete([])

    @patch("procurement_agent.openrouter.urlopen")
    def test_rejects_malformed_provider_response(self, send):
        for payload in (None, [], {"choices": []}, {"choices": [None]}, {"choices": ["bad"]}):
            send.return_value.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
            with self.subTest(payload=payload), self.assertRaisesRegex(OpenRouterError, "no usable"):
                self.client.complete([])

    @patch("procurement_agent.openrouter.urlopen")
    def test_timeout_is_explicit(self, send):
        for error in (TimeoutError(), URLError(TimeoutError())):
            send.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaisesRegex(OpenRouterError, "timed out.*60s"):
                self.client.complete([])

    @patch.dict("os.environ", {}, clear=True)
    @patch("sys.stderr", new_callable=io.StringIO)
    def test_cli_missing_credentials(self, stderr):
        self.assertEqual(main(["check"]), 1)
        self.assertIn("OPENROUTER_API_KEY", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

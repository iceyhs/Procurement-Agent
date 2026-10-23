import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from procurement_agent.cli import main
from procurement_agent.openrouter import OpenRouterClient, OpenRouterError
from procurement_agent.schema import extraction_format


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
        self.assertNotIn("response_format", json.loads(request.data))
        self.assertNotIn("temperature", json.loads(request.data))
        self.assertNotIn("provider", json.loads(request.data))
        self.assertNotIn("test-secret", repr(self.client))

    @patch("procurement_agent.openrouter.urlopen")
    def test_structured_request_includes_schema_and_requires_parameter_support(self, send):
        send.return_value.__enter__.return_value = io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        }).encode())
        contract = extraction_format(["supplier_1"])
        self.client.complete([], response_format=contract)
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(body["response_format"], contract)
        self.assertEqual(body["temperature"], 0)
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(body["provider"], {"require_parameters": True})

    @patch("procurement_agent.openrouter.urlopen")
    def test_unsupported_structured_output_does_not_fall_back(self, send):
        send.side_effect = HTTPError("url", 404, "sensitive-provider-body", {}, None)
        with self.assertRaisesRegex(OpenRouterError, "supporting response_format=json_schema") as error:
            self.client.complete([], response_format=extraction_format(["supplier_1"]))
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("sensitive-provider-body", str(error.exception))

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
        with self.assertRaisesRegex(OpenRouterError, "output token limit"):
            self.client.complete([])

    @patch("procurement_agent.openrouter.urlopen")
    def test_invalid_provider_json_raises_controlled_error_without_retry(self, send):
        send.return_value.__enter__.return_value = io.BytesIO(b"not JSON")
        with self.assertRaisesRegex(OpenRouterError, "OpenRouter returned invalid JSON"):
            self.client.complete([])
        self.assertEqual(send.call_count, 1)

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

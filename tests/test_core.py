from __future__ import annotations

from dataclasses import dataclass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from silvergun.client import OpenAICompatibleClient
from silvergun.router import CapabilityRouter, ExternalCapability


@dataclass
class Settings:
    normalized_base_url: str
    model: str = "fast-model"
    timeout_seconds: int = 5


class ProviderHandler(BaseHTTPRequestHandler):
    last_authorization = ""
    last_body = {}

    def do_GET(self):
        if self.path == "/v1/models":
            self._json({"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "a-model"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        ProviderHandler.last_authorization = self.headers.get("Authorization", "")
        ProviderHandler.last_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_function_context", "arguments": "{}"}}]}}]})

    def _json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()

    def test_models_are_deduplicated_and_sorted(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        self.assertEqual(client.list_models(), ["a-model", "z-model"])

    def test_chat_uses_standard_tool_payload(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        completion = client.chat("fast-model", [{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "get_function_context", "parameters": {"type": "object"}}}])
        self.assertEqual(completion.tool_calls[0]["function"]["name"], "get_function_context")
        self.assertEqual(ProviderHandler.last_authorization, "Bearer test-key")
        self.assertEqual(ProviderHandler.last_body["tool_choice"], "auto")


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.capabilities = [
            ExternalCapability("cmd_1", "Decompiler/Graph", "Render a control flow graph", False),
            ExternalCapability("cmd_2", "Patcher/Assemble", "Assemble and apply patches", True),
        ]

    def test_patch_route_stays_narrow(self):
        route = CapabilityRouter().route("Patch this function to bypass the check", self.capabilities)
        self.assertEqual(route.intent, "patch")
        self.assertEqual(route.tools[:2], ("get_function_context", "apply_patch"))
        self.assertLessEqual(len(route.external), 1)

    def test_explicit_plugin_query_selects_only_relevant_extensions(self):
        route = CapabilityRouter().route("Use a plugin to render the control flow graph", self.capabilities)
        self.assertEqual(route.intent, "plugins")
        self.assertIn("invoke_external_command", route.tools)
        self.assertEqual(route.external[0].identifier, "cmd_1")


if __name__ == "__main__":
    unittest.main()

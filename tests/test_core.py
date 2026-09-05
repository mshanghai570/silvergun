from __future__ import annotations

from dataclasses import dataclass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.client import OpenAICompatibleClient, ProviderError
from _silvergun.router import CapabilityRouter, ExternalCapability


@dataclass
class Settings:
    normalized_base_url: str
    model: str = "fast-model"
    timeout_seconds: int = 5
    ca_bundle: str = ""


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
        if ProviderHandler.last_body["model"] == "provider-alias":
            if "max_tokens" in ProviderHandler.last_body:
                self._json({"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."}}, status=400)
                return
            if "temperature" in ProviderHandler.last_body:
                self._json({"error": {"message": "Unsupported parameter: 'temperature' is not supported with this model."}}, status=400)
                return
        if ProviderHandler.last_body["model"] == "legacy-gpt-5" and "max_completion_tokens" in ProviderHandler.last_body:
            self._json({"error": {"message": "Unsupported parameter: 'max_completion_tokens' is not supported by this gateway."}}, status=400)
            return
        self._json({"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_function_context", "arguments": "{}"}}]}}]})

    def _json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
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

    def test_invalid_ca_bundle_fails_closed(self):
        with self.assertRaisesRegex(ProviderError, "CA bundle path does not exist"):
            OpenAICompatibleClient(Settings(self.base_url, ca_bundle="/definitely/missing/silvergun-ca.pem"), "test-key")

    def test_models_are_deduplicated_and_sorted(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        self.assertEqual(client.list_models(), ["a-model", "z-model"])

    def test_chat_uses_standard_tool_payload(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        completion = client.chat("fast-model", [{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "get_function_context", "parameters": {"type": "object"}}}])
        self.assertEqual(completion.tool_calls[0]["function"]["name"], "get_function_context")
        self.assertEqual(ProviderHandler.last_authorization, "Bearer test-key")
        self.assertEqual(ProviderHandler.last_body["tool_choice"], "auto")

    def test_modern_openai_models_use_supported_parameters(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        client.chat("gpt-5-mini", [{"role": "user", "content": "hi"}])
        self.assertEqual(ProviderHandler.last_body["max_completion_tokens"], 1400)
        self.assertNotIn("max_tokens", ProviderHandler.last_body)
        self.assertNotIn("temperature", ProviderHandler.last_body)

    def test_provider_alias_recovers_from_parameter_rejections(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        client.chat("provider-alias", [{"role": "user", "content": "hi"}])
        self.assertEqual(ProviderHandler.last_body["max_completion_tokens"], 1400)
        self.assertNotIn("max_tokens", ProviderHandler.last_body)
        self.assertNotIn("temperature", ProviderHandler.last_body)

    def test_legacy_gateway_can_use_a_modern_model_alias(self):
        client = OpenAICompatibleClient(Settings(self.base_url), "test-key")
        client.chat("legacy-gpt-5", [{"role": "user", "content": "hi"}])
        self.assertEqual(ProviderHandler.last_body["max_tokens"], 1400)
        self.assertEqual(ProviderHandler.last_body["temperature"], 0.1)
        self.assertNotIn("max_completion_tokens", ProviderHandler.last_body)


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

<<<<<<< HEAD
    def test_string_search_request_selects_binary_ninja_string_tools(self):
        route = CapabilityRouter().route("Find all strings containing password in this binary", [])
        self.assertEqual(route.intent, "strings")
        self.assertIn("bn_search_strings", route.tools)

    def test_url_hunt_request_selects_binary_ninja_string_tools(self):
        route = CapabilityRouter().route("Search the binary for urls and http endpoints", [])
        self.assertEqual(route.intent, "strings")
        self.assertIn("bn_search_strings", route.tools)

    def test_symbol_search_request_selects_symbol_tools(self):
        route = CapabilityRouter().route("Search symbols for parse_header", [])
        self.assertEqual(route.intent, "symbols")
        self.assertIn("bn_search_symbols", route.tools)

    def test_vulnerability_request_still_wins_over_string_tools(self):
        route = CapabilityRouter().route("Find format string vulnerabilities in this function", [])
        self.assertEqual(route.intent, "vulnerabilities")
        self.assertNotEqual(route.tools[0], "bn_search_strings")

    def test_patch_request_still_routes_to_patch(self):
        route = CapabilityRouter().route("Patch this function to bypass the check", self.capabilities)
        self.assertEqual(route.intent, "patch")

    def test_compound_find_and_patch_request_keeps_mutation_tool(self):
        route = CapabilityRouter().route("I want to search for the binary vulnerabilities. Find the correct functions and patch them.", [])
        self.assertEqual(route.intent, "vulnerabilities")
        self.assertIn("get_function_context", route.tools)
        self.assertIn("apply_patch", route.tools)

    def test_continue_case_directive_gets_case_file_tools(self):
        route = CapabilityRouter().route("Continue the investigation from the restored case file. Review unresolved questions and choose the highest-value next evidence to collect.", [])
        self.assertEqual(route.intent, "continue")
        self.assertIn("notebook_context", route.tools)
        self.assertIn("get_function_context", route.tools)

=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

if __name__ == "__main__":
    unittest.main()

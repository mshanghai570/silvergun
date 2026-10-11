from __future__ import annotations

from dataclasses import dataclass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.client import OpenAICompatibleClient, ProviderError, _extract_legacy_tool_calls
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

    def test_legacy_xml_tool_markup_is_promoted_to_a_tool_call(self):
        content = "Key observation: strings found. <tool_call>tool_call>bn_search_strings<arg_key>pattern</arg_key><arg_value>https://</arg_value><arg_key>max_results</arg_key><arg_value>30</arg_value></tool_call>"
        cleaned, calls = _extract_legacy_tool_calls(content)
        self.assertEqual(cleaned, "Key observation: strings found.")
        self.assertEqual(calls[0]["function"]["name"], "bn_search_strings")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"])["max_results"], 30)

    def test_malformed_protocol_is_a_provider_error_not_assistant_text(self):
        with self.assertRaises(ProviderError):
            _extract_legacy_tool_calls("The model stopped at <tool_call><arg_key>query</arg_key>")

    def test_json_tool_envelope_is_normalized_at_provider_boundary(self):
        cleaned, calls = _extract_legacy_tool_calls('{"tool_calls":[{"id":"1","function":{"name":"bn_search_symbols","arguments":"{}"}}]}')
        self.assertEqual(cleaned, "")
        self.assertEqual(calls[0]["function"]["name"], "bn_search_symbols")



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

    def test_broad_function_search_exposes_all_search_providers(self):
        route = CapabilityRouter().route("Search all plugins and Binary Ninja for functions related to authentication", [])
        self.assertEqual(route.intent, "search")
        for tool in ("search_capabilities", "invoke_external_command", "semantic_search", "query_binary", "bn_find_functions", "bn_search_symbols", "boolhunter_quick_scan"):
            self.assertIn(tool, route.tools)

    def test_plugin_type_search_does_not_require_boolhunter(self):
        route = CapabilityRouter().route("Find a plugin that can search for network functions", [])
        self.assertEqual(route.intent, "search")
        self.assertEqual(route.tools[0], "get_function_context")
        self.assertIn("search_capabilities", route.tools)
        self.assertIn("invoke_external_command", route.tools)

    def test_purchase_search_uses_category_discovery(self):
        route = CapabilityRouter().route("Find purchase related functions", [])
        self.assertEqual(route.intent, "category")
        self.assertIn("boolhunter_find_category", route.tools)
        self.assertIn("semantic_search", route.tools)

    def test_exact_related_function_requests_stay_focused(self):
        for request in (
            "Find functions related to StoreKit purchases.",
            "Find functions related to networking.",
            "Find functions related to authentication.",
        ):
            route = CapabilityRouter().route(request, [])
            self.assertEqual(route.intent, "category")
            self.assertEqual(route.tools, ("semantic_search", "boolhunter_find_category"))

    def test_open_binary_information_request_uses_metadata(self):
        route = CapabilityRouter().route("Show me information about the currently opened binary.", [])
        self.assertEqual(route.intent, "metadata")
        self.assertEqual(route.tools, ("bn_get_metadata",))

    def test_named_plugin_request_prioritizes_plugin_execution(self):
        capabilities = [ExternalCapability("advanced", "Advanced Search", "Search functions by semantic category and query", True)]
        route = CapabilityRouter().route("Use Advanced Search plugin to help find purchase functions", capabilities)
        self.assertEqual(route.intent, "search")
        self.assertIn("search_capabilities", route.tools)
        self.assertIn("invoke_external_command", route.tools)
        self.assertEqual(route.external[0].identifier, "advanced")

    def test_smart_patch_route_is_mutation_specific(self):
        route = CapabilityRouter().route("Review this function for a precise smart patch. Explain the fix first.", [])
        self.assertEqual(route.intent, "patch")
        self.assertEqual(route.tools[:2], ("get_function_context", "apply_patch"))

    def test_assembly_patch_request_exposes_disassemble_and_assembler(self):
        route = CapabilityRouter().route("Assemble an instruction patch to NOP the check", [])
        self.assertEqual(route.intent, "patch")
        self.assertEqual(route.tools[:2], ("get_function_context", "apply_patch"))
        self.assertIn("disassemble", route.tools)
        self.assertIn("apply_assembly_patch", route.tools)

    def test_undo_request_exposes_patch_history_and_undo(self):
        route = CapabilityRouter().route("Undo the last patch on this binary", [])
        self.assertEqual(route.intent, "patch")
        self.assertIn("undo_last_patch", route.tools)
        self.assertIn("patch_history", route.tools)

    def test_explicit_xref_request_uses_xref_route(self):
        route = CapabilityRouter().route("Analyze this function's callers and callees", [])
        self.assertEqual(route.intent, "xrefs")
        self.assertIn("get_xrefs", route.tools)

    def test_router_does_not_treat_substrings_as_intents(self):
        self.assertEqual(CapabilityRouter().route("Explain the anatomy of this function", []).intent, "explain")
        self.assertNotEqual(CapabilityRouter().route("A mapless string literal", []).intent, "map")
        self.assertEqual(CapabilityRouter().route("Please rename this function", []).intent, "rename")

    def test_natural_language_outcomes_route_to_the_requested_action(self):
        cases = (
            ("Could you make this function always return true?", "patch", "apply_patch"),
            ("Give this function a meaningful name", "rename", "rename_function"),
            ("Set this function's signature based on its arguments", "types", "apply_function_type"),
            ("Leave a comment explaining the authentication check", "annotate", "annotate_function"),
            ("What calls this function?", "xrefs", "get_xrefs"),
            ("Show me the hardcoded API endpoints", "strings", "bn_search_strings"),
        )
        for request, intent, tool in cases:
            with self.subTest(request=request):
                route = CapabilityRouter().route(request, [])
                self.assertEqual(route.intent, intent)
                self.assertIn(tool, route.tools)

    def test_natural_language_patch_outcome_keeps_discovery_and_mutation(self):
        route = CapabilityRouter().route("Find the license check and make it always return true", [])
        self.assertEqual(route.intent, "patch")
        self.assertIn("find_functions", route.tools)
        self.assertIn("apply_patch", route.tools)

    def test_rollback_phrase_routes_to_undo(self):
        route = CapabilityRouter().route("Go back to before the last patch", [])
        self.assertEqual(route.intent, "patch")
        self.assertIn("undo_last_patch", route.tools)

    def test_find_callers_is_not_mistaken_for_a_compound_mutation(self):
        route = CapabilityRouter().route("Find every function that calls this one", [])
        self.assertNotIn("apply_patch", route.tools)


if __name__ == "__main__":
    unittest.main()

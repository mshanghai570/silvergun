# Silvergun / Binary Ninja Interaction Profile

## Scope and conclusion

This profile traces the normal Silvergun investigation path from the active BinaryView through capability discovery, evidence collection, and optional remote fan-out. Silvergun does not directly integrate with or disable Rikugan. The principal coexistence risks were **unnecessary HLIL materialization during request setup**, **third-party adapter construction from a background task**, and **duplicate BinaryView function enumeration in BoolHunter**. The implementation now avoids those patterns while preserving existing capability routing and approval gates.

Binary Ninja Python API work is serialized through `execute_on_main_thread_and_wait` in the native tool layer and through the adapter registry's host-thread bridge. Remote fan-out operates only on immutable snapshots and does not pass BinaryView or Function handles to worker threads.

## Normal investigation path

| Phase | Silvergun operation | BinaryView interaction | Analysis/wait behavior |
| --- | --- | --- | --- |
| Sidebar context | Resolve active view and selected function | `get_function_containing(offset)`; display reads such as filename, architecture, platform, and function address | Read-only host access; may acquire the host read lock, but no explicit analysis request |
| Capability discovery | Refresh external plugin commands | `PluginCommand.get_valid_list(PluginCommandContext(bv))` | Executes Binary Ninja's command-validity path. Third-party validity code is outside Silvergun's control; results are cached by view/context fingerprint |
| Adapter discovery | Initialize Binary Ninja and optional BoolHunter adapters | Adapter construction receives the active BinaryView | Now marshaled to the Binary Ninja host thread. Silvergun does not call Rikugan or enumerate its data directly |
| Request context | Build the compact context header | Reads file metadata, architecture, platform, format, image base, entry point, `analysis_changed`, function count, and selected function name/type/address | No eager HLIL materialization after the optimization |
| Planner/router | Select capabilities and validate the plan | None | No BinaryView traversal |
| Function context | Read selected function evidence | Function address/name/type; parameters/locals; callers/callees; HLIL instruction traversal | HLIL access can cause deferred IL materialization or wait for analysis. It is now cached per function for the investigation |
| Function search | Find name matches | Iterates `bv.functions`; reads name and size | Read-only traversal; bounded by result count but currently scans until the end of the function list |
| Semantic search/query | Build the bounded triage index | One bounded `bv.functions` materialization; reads function name/type and HLIL text | First use may materialize HLIL for up to `MAX_TRIAGE_FUNCTIONS`; later semantic/query calls reuse the in-memory index |
| Xrefs/code map | Traverse relationships | Reads `function.callers` and `function.callees`; bounded by depth/items | Read-only graph traversal; no explicit analysis trigger |
| String search | Scan strings and resolve references | `bv.get_strings()`; for matches, `bv.get_code_refs(string_address)` | String enumeration and code-reference lookup may wait for relevant analysis state; bounded to 100 matches and 20 reference lookups |
| Symbol search | Search symbols | Reads symbol collections exposed by the BinaryView | Read-only; no explicit `analyze()` call |
| Types/comments/tags | Read metadata | Reads function type, variables, comments, tags, or bounded function slices | Read-only; full-binary variants are bounded but can still traverse 100–1,000 functions |
| Explicit analysis | `bn_analyze` | Resolves function and calls `Function.analyze()`, or explicitly analyzes up to 1,000 functions for `full_analysis=True` | This is the only Silvergun operation that explicitly requests analysis. It can consume substantial CPU and compete with other analysis-heavy plugins |
| Decompilation | `bn_decompile` | Resolves function and iterates `func.hlil` | May wait for deferred analysis/HLIL materialization; output is bounded, but Binary Ninja's Python API does not expose a real timeout |
| BoolHunter | Quick/category/batch analysis | Iterates bounded function lists and invokes BoolHunter's engine | Plugin engine behavior is external. Quick/category scans now use one materialized bounded function list instead of counting and traversing the view twice |
| External plugin command | Approved `invoke_external_command` | Calls the plugin's `execute(PluginCommandContext)` on the BN host thread | Behavior is plugin-defined and may mutate or trigger analysis. Silvergun keeps the existing approval gate and does not auto-run arbitrary commands |
| Remote fan-out | Snapshot functions, then submit model reviews | Snapshot creation is host-thread marshaled; worker threads receive plain dictionaries only | No concurrent BinaryView API access from worker threads |

## Redundancy and concurrency findings

### Corrected

1. **Eager HLIL work during context construction.** `NativeTools.context_hint()` previously called the full function snapshot, including HLIL iteration, before the model selected any evidence tool. It now emits a lightweight function header. This removes an unnecessary decompilation/analysis wait for requests that do not need the current function.
2. **Repeated snapshots of the same function.** `get_function_context`, vulnerability hints, verification, and fan-out preparation could each walk the same HLIL. A per-investigation address-keyed snapshot cache now reuses immutable snapshots.
3. **Background third-party adapter discovery.** `AgentTask` can run off the UI thread. `AdapterRegistry.discover()` now enters through the Binary Ninja host-thread bridge, including BoolHunter construction and any third-party adapter initialization.
4. **Duplicate BoolHunter function enumeration.** Quick and category scans previously computed `len(list(bv.functions))` and then traversed `bv.functions[:2000]` again. Each now materializes one bounded list and uses it for both counting and scanning.

### Preserved and intentionally bounded

- Native tool calls remain serialized through the BN main-thread bridge.
- Adapter calls remain serialized through `on_binary_ninja_thread`.
- Remote review concurrency remains safe because workers receive frozen snapshot dictionaries, not Binary Ninja objects.
- Cross-reference traversal has depth and node limits.
- String reference expansion is capped.
- Full analysis remains available only when the model explicitly requests `full_analysis`; the existing default is current-function analysis rather than whole-binary analysis.
- Mutation operations remain approval-gated and host-thread serialized.

## Rikugan coexistence assessment

Rikugan is not disabled, removed, or invoked by Silvergun. Silvergun's interaction with another installed plugin is limited to Binary Ninja's plugin-command validity enumeration and an explicitly approved callable command selected by the model. This is the safe boundary for coexistence:

- Silvergun does not modify global Binary Ninja analysis settings.
- Silvergun does not start a second analysis scheduler.
- Silvergun does not call Rikugan-specific APIs or inspect Rikugan-owned state.
- Silvergun does not pass live BinaryView/Function objects to remote worker threads.
- Plugin command discovery is cached by BinaryView/context, reducing repeated validity callbacks while preserving context changes.
- If a third-party command is selected, its execution remains explicit and approval-gated because its analysis and mutation behavior cannot be inferred from the command name alone.

On a resource-constrained Intel Mac, the remaining potentially expensive operations are intentional evidence requests: first-use semantic triage/HLIL indexing, explicit `bn_analyze`, decompilation, broad comments/tags/types scans, and third-party commands. These should be visible in Activity and should not be silently duplicated by Silvergun setup code.

## Validation

The optimization changes were validated with Python compile checks, the complete existing test suite, and new regression tests proving that context construction does not access HLIL and that repeated evidence requests reuse one native snapshot.

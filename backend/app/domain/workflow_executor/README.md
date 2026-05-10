# `workflow_executor` package

Orchestration for running a **`WorkflowDefinition`** graph: validation, scheduling waves, executing nodes, nested workflows, and emitting lifecycle payloads for SSE consumers.

## Control flow

1. **`WorkflowExecutor`** ([`executor.py`](executor.py)) — **`run()`** (sync/no persistence), **`execute_scheduled_run()`** for persisted **`WorkflowRun`** rows + optional **`sse_publish`**, graph validation (**global cycle detection** omits **`TryCatchControlNode` `value`** wires — see **`_edges_for_global_cycle_detection`**), semaphore + wave caps, resolved **[`ExecutionLimits`](../execution_limits.py)** (**TTL**, **max node executions / loop iterations / nested depth**), run logging.
2. **Dispatch** ([`dispatch/`](dispatch/) / [`dispatch/execute_node_dispatch.py`](dispatch/execute_node_dispatch.py)) — `_execute_node` routes each parsed node (`isinstance` ladder) to existing instance methods (`_resolve_*`, `_await _run_*` skills).
3. **Mixins** (same semantics as a single class; kept for file size):
   - [`skills_runner_mixin.py`](skills_runner_mixin.py) — async `_run_*` skills (LLM, multimodal, TTS, transcribe, Gmail/Calendar, fetch URL, snapshots, …). External calls resolve through the `executor` module where tests patch symbols (see `WorkflowExecutorSkillsRunnerMixin._exec_skill_deps`).
   - [`executor_resolver_mixin.py`](executor_resolver_mixin.py) — `_resolve_*` value/control paths, For-loop runners, `_resolve_workflow_node`, Stop/Start primitives.
4. **Satellites** — [`parsing.py`](parsing.py) (`_parse_node`), [`inputs.py`](inputs.py), [`graph.py`](graph.py), [`fetch_url_runtime.py`](fetch_url_runtime.py), [`capture_url_snapshot_runtime.py`](capture_url_snapshot_runtime.py), [`multimodal_llm_runtime.py`](multimodal_llm_runtime.py), [`html_parse_basic.py`](html_parse_basic.py), [`gmail_llm_prompt.py`](gmail_llm_prompt.py), [`schema_normalizer.py`](schema_normalizer.py), [`diagnostics.py`](diagnostics.py), etc.

## Maintainer map (skill/control families → module)

| Area | Primary module |
|------|----------------|
| Parsed node → executor route | [`dispatch/execute_node_dispatch.py`](dispatch/execute_node_dispatch.py) |
| LLM / multimodal / TTS / transcribe / Google list skills | [`skills_runner_mixin.py`](skills_runner_mixin.py) |
| Primitives, utilities, controls, sandbox grid, workflows, loops | [`executor_resolver_mixin.py`](executor_resolver_mixin.py) |
| Graph validation / topo sort / for-loop + try/catch topology | [`graph.py`](graph.py) |
| Execution limits (defaults, merge, ceilings) | [`../execution_limits.py`](../execution_limits.py) (+ [`config.py`](../../core/config.py) `WORKFLOW_EXECUTION_*`, `WORKFLOW_*_LOOP_BATCH_*`) |
| Upstream wiring & slot resolution | [`inputs.py`](inputs.py) |

Adding a node type follows [§ Adding a workflow node type](../../../../docs/ARCHITECTURE.md) (schemas → `parsing` → dispatch ladder → palettes / SPA parity tests).

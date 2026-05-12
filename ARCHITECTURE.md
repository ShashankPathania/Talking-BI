# ARCHITECTURE

## Model Design

The backend is organized around a canonical `QueryState` object with six layers:

- `intent`: what the user is trying to do
- `data`: which source is attached and what schema is available
- `transformation`: filters, grouping, aggregation, sorting, and limits
- `analysis`: requested analytical behaviors such as trend or anomaly detection
- `visualization`: chart type and chart mapping
- `meta`: query/version tracking

Supporting models:

- `SessionState`: persistent multi-turn session state with messages and last result
- `QueryResult`: execution-grounded data payload with schema and optional SQL
- `ExecutionPlan`: planner output describing fetch reuse vs recomputation
- `BIResponse`: API response contract combining explanation, insights, chart, preview, and query state
- `KpiCard` and `ReportSection`: product-facing response models that let the frontend show KPI snapshots and structured report narratives instead of only raw debug/state dumps
- `DatasetProfile`: persisted metadata for uploaded datasets
- `FOUNDATION_BRIEF.md`: the preserved original system brief and expected end-state used as a product reference
- `ResultCache`: file-backed cache for execution results keyed by deterministic query-state fingerprints
- `QueryHistoryEntry`: persisted lineage record for each query-state version within a session
- Browser MVP: a built-in FastAPI-served frontend that exercises uploads, sessions, queries, Plotly charts, and state inspection from the same backend
- `LLMReasoningService`: provider-routed reasoning layer that uses Groq for heavier tasks and OpenRouter for lighter tasks while keeping execution grounded in code
- `DataPreparationService`: preprocessing layer that normalizes uploaded columns, profiles missing values and duplicates, coerces likely dates/numerics, and computes raw-data outlier counts

## Data Flow

1. A user uploads a CSV or Excel file, which is stored under `storage/datasets/` and registered in `datasets.json`.
1. A user can also register a database table, which is stored as dataset metadata in the same registry.
2. Uploaded files are preprocessed into canonical column names with alias mappings before they are used for reasoning or execution.
3. A user can open `/` to use the built-in browser UI, which calls the same FastAPI APIs.
4. A user sends a natural-language query to `/v1/query`.
5. `ConversationManager` loads the prior `SessionState` or creates a new one.
6. If a dataset is attached, `DatasetService` injects dataset metadata into the `data` layer.
7. `LLMReasoningService.infer_schema` can infer likely metrics, dimensions, and the time column from the schema before execution.
8. `QueryStateUpdater` applies a deterministic baseline incremental state update.
9. `LLMReasoningService` can act as the primary interpreter and map user language onto the canonical dataset schema.
10. `QueryPlanner` compares previous vs current state sections and decides whether to:
   - fetch new data
   - reuse the previous result
   - rerun analysis
   - update visualization only
11. `LLMReasoningService.refine_plan` can refine the planner output, but deterministic safety checks remain authoritative.
12. `UnifiedExecutor` routes execution to pandas or SQL and resolves registered database metadata into executable connection details.
    For file-backed datasets, pandas execution can now expose the uploaded file as a temporary SQLite table so validated LLM-authored SQL can still be executed safely.
13. If execution fails due to schema or query mismatch, `ConversationManager` converts the failure into user-facing warnings instead of a hard API error.
14. `DatabaseConnector` centralizes URL validation, schema introspection, table loading, and SQL execution.
15. `ResultCache` checks whether an identical query-state fingerprint already has a stored result.
16. Execution results now include lightweight profiling metadata such as numeric ranges and means.
17. `InsightEngine` produces execution-grounded insights including metric ranges, trend deltas, comparison leaders, ranked anomaly summaries, correlation summaries, and raw-data quality flags.
18. `InsightEngine` also derives KPI cards and report sections from the grounded result/profile so the frontend can present a business-friendly summary.
19. `PlotlyBuilder` creates a chart payload from result data and visualization state, and can also produce a richer multi-chart dashboard for dataset-report requests.
20. `LLMReasoningService.build_grounded_explanation` can turn the grounded outputs into a smarter final explanation.
21. The updated session and its query-history lineage are written back to `storage/sessions/`.
22. A conversational guardrail path intercepts non-analytical turns such as greetings/help prompts and returns assistant guidance without attempting SQL or pandas execution.

## Current Boundaries

- File-backed analytics are implemented.
- SQLite-backed database registration and execution are implemented.
- PostgreSQL/MySQL connector dependencies are installed in the local venv and the code path is connector-ready, but live coverage is still pending.
- PostgreSQL/MySQL live integration tests are present and can be enabled with environment variables, but they still need real database targets to validate against.
- State updates are still heuristic, but are now schema-aware when dataset metadata is available and fall back to common BI fields when no schema is attached yet.
- Visualization-only follow-ups are supported and can reuse prior results without refetching data.
- Numeric filter extraction and lightweight profiling are implemented, though parsing is still heuristic rather than model-driven.
- Insight generation is execution-grounded, but the anomaly logic is still lightweight and should evolve into stronger statistical detection beyond the current ranked z-score heuristic.
- Identical query states can now reuse cached results through file-backed caching in `storage/result_cache/`.
- Sessions now preserve query lineage so prior versions and parent-child refinement chains can be inspected.
- Correlation prompts are supported with scatter-chart configuration and simple correlation summaries.
- A built-in frontend is now available for end-to-end MVP testing, but it is still a thin product shell rather than a polished production UI.
- LLM reasoning is now integrated as an optional hybrid layer. If provider keys are missing or an API call fails, the system falls back to deterministic reasoning so the product remains usable.
- Uploaded CSV/Excel datasets now receive a virtual table name, which allows the LLM to generate read-only SQL for file-backed analysis as well as live database analysis.
- The browser UI is now moving beyond a debug console shape: it can render KPI cards, structured report sections, and multi-chart dataset summaries, although the interaction model is still early-stage.
- The browser UI now includes both file upload and database registration entry points, backed by the same dataset registry and session flow.

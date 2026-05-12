# Talking BI v2 - Project Reference

## 1. Project Identity

`Talking BI v2` is a conversational business intelligence system built as a local-first Python web application. Its main purpose is to let a user bring structured data into the system, ask natural-language analytical questions, and receive grounded outputs such as:

- explanations
- charts
- KPI-style summaries
- data previews
- session-aware follow-up responses
- debugging context about how the answer was produced

At a product level, the project sits at the intersection of:

- conversational analytics
- lightweight BI tooling
- autonomous agent workflows
- local data exploration
- LLM-assisted but execution-grounded reporting

The project is not just "chat with data." Its design intent is more specific:

1. Normalize and profile incoming datasets so the system has a canonical representation.
2. Maintain a structured analytical state across multiple turns.
3. Route user prompts either to a simple conversational reply path or to an agentic analytical loop.
4. Keep data execution grounded in SQL and dataframe operations instead of letting the LLM fabricate answers.
5. Provide a built-in browser UI so the whole workflow can be tested end-to-end without a separate frontend app.

In practical terms, this project behaves like a prototype analytics copilot for uploaded spreadsheets and selected database tables.

## 2. What the Project Does

### Core capabilities

The current codebase supports these user-visible workflows:

1. Upload a `CSV` or `Excel` file.
2. Register an external database table as a dataset.
3. Persist dataset metadata locally.
4. Start a query session tied to a dataset.
5. Ask natural-language BI questions.
6. Generate a grounded answer using an agent loop and SQL-backed observations.
7. Render a primary Plotly chart and optionally additional charts.
8. Return a data preview and insight objects.
9. Save session state and message history locally.
10. Re-open prior sessions from the built-in UI.
11. Inspect debug information such as query state and SQL/debug metadata.
12. Export the visible dashboard view to PDF through the browser print flow.

### Typical use cases implied by the code

- "Show revenue trends by region"
- "Compare sales across categories"
- "Find anomalies"
- "Show correlation between sales and revenue"
- "Give me a full dataset report"
- "Make it quarterly"
- "Switch to a different session and continue the analysis"

### Product philosophy

The README and implementation both show an important design principle: the LLM is used as a reasoning layer, but the actual data work is intended to be grounded in executable operations. The project repeatedly emphasizes:

- deterministic planning
- structured query state
- read-only SQL
- execution-grounded BI responses
- hybrid LLM reasoning rather than unrestricted free-form generation

That makes this project stronger than a generic chatbot wrapper, because it tries to separate reasoning from execution.

## 3. High-Level Architecture

The repository is organized as a monolithic FastAPI application with internal modular layers.

### Main layers

1. **Presentation layer**
   - FastAPI endpoints
   - static browser UI served from the backend

2. **Core domain layer**
   - state models for intent, data, transformations, analysis, visualization, session state, and response payloads

3. **Dataset ingestion and storage layer**
   - file upload handling
   - preprocessing
   - DuckDB ingestion
   - metadata persistence in SQLite

4. **Agent and reasoning layer**
   - query classifier
   - agent planner
   - autonomous execution loop
   - tool registry
   - hybrid LLM client

5. **Execution layer**
   - SQL execution helpers
   - pandas execution helpers
   - visualization generation
   - insight generation

6. **Persistence and memory layer**
   - session JSON files
   - metadata SQLite DB
   - cache SQLite DB
   - result cache files

### Architectural style

This is best described as:

- a monolith
- modular service-oriented internals
- local persistence
- server-rendered static frontend delivery
- agent-based orchestration over analytic tools

It is not:

- a microservice system
- a multi-page frontend framework app
- a cloud-native distributed platform
- an authenticated enterprise SaaS product

## 4. Repository and Component Map

## Application entry

### `app/main.py`

This is the FastAPI entrypoint. It:

- creates the FastAPI app
- includes all API routers
- mounts the static web directory at `/static`
- serves a health endpoint

Routes included:

- frontend routes
- query routes
- upload routes
- session routes
- system routes

## API routes

### `app/api/routes/frontend.py`

Serves the built-in browser UI at `/`.

### `app/api/routes/query.py`

Exposes the main analytics endpoint:

- `POST /v1/query`

This is the core request entrypoint for conversational BI.

### `app/api/routes/upload.py`

Exposes dataset management endpoints:

- `GET /v1/datasets`
- `POST /v1/datasets/upload`
- `POST /v1/datasets/register-database`

### `app/api/routes/session.py`

Exposes session inspection endpoints:

- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`

### `app/api/routes/system.py`

Exposes runtime/system configuration visibility:

- `GET /v1/system/status`

## API schemas

### `app/api/schemas/query.py`

Defines:

- `DataSourceRef`
- `QueryRequest`

Important detail: `QueryRequest` supports `message`, `session_id`, `dataset_id`, and `data_source`.

However, in the current runtime path, `dataset_id` is the important field actually used by `ConversationManager`. The presence of `data_source` looks like a legacy or partially retained contract rather than a fully active pathway.

### `app/api/schemas/response.py`

Aliases the response contract to `BIResponse`.

### `app/api/schemas/dataset.py`

Defines response models for:

- uploaded/registered dataset payloads
- dataset lists
- database registration
- session list and session detail payloads

## Core models

### `app/core/config.py`

Defines environment-backed `Settings`. This is the single source of truth for:

- app name
- storage paths
- result limits
- session TTL
- LLM mode
- provider keys and model names

### `app/core/state.py`

This is one of the most important files in the project. It defines the structured analytical state model and the response model. It includes:

- `IntentLayer`
- `ColumnProfile`
- `DataLayer`
- `TransformationLayer`
- `AnalysisLayer`
- `VisualizationLayer`
- `MetaLayer`
- `QueryState`
- `ChatMessage`
- `QueryResult`
- `InsightItem`
- `KpiCard`
- `ReportSection`
- `ExecutionPlan`
- `QueryHistoryEntry`
- `SessionState`
- `ChartPayload`
- `DebugPayload`
- `AgentReflection`
- `BIResponse`

This file represents the core domain model of the whole system.

### `app/core/dataset.py`

Defines `DatasetProfile`, the canonical metadata object describing a registered dataset.

## Services

### `app/services/conversation_manager.py`

This is the runtime orchestrator for the analytics experience.

Responsibilities:

- load or create session state
- append user messages
- attach dataset metadata into query state
- classify the incoming prompt
- choose simple reply path vs agentic path
- invoke the autonomous agent loop
- collect tool outputs into a final response
- build charts from generated chart configs
- generate final insights
- persist updated session state

This is the operational heart of the app.

### `app/services/datasets.py`

Handles dataset registration and loading.

Responsibilities:

- validate uploaded file types
- save uploaded files to disk
- load CSV/Excel into pandas
- preprocess columns and data types
- create canonical namespaced DuckDB table names
- ingest file-backed data into DuckDB
- create `DatasetProfile`
- save dataset metadata into SQLite
- inspect and register database datasets
- load file-backed or database-backed dataframes on demand
- attach dataset metadata into `QueryState`

### `app/services/data_preparation.py`

Normalizes raw tabular data before use.

Responsibilities:

- canonicalize column names
- generate alias maps
- infer numeric columns
- infer datetime columns
- compute missing value counts
- compute duplicate row counts
- compute simple outlier counts
- preserve original display labels

This preprocessing step is important because it improves LLM grounding and query robustness.

### `app/services/db_connectors.py`

Provides SQLAlchemy-based database helpers for:

- SQLite
- PostgreSQL
- MySQL

Responsibilities:

- validate database URLs
- normalize URLs to the correct SQLAlchemy driver
- inspect schema
- count rows
- sample rows
- execute SQL
- quote identifiers safely per dialect

### `app/services/planner.py`

Defines `QueryPlanner`, a deterministic planner that compares previous and current state and decides whether to:

- fetch new data
- reuse prior data
- update only the visualization

This looks like part of an older or alternate execution pathway. It is still used for the simple conversational branch, but not as the main planner for the current active agentic loop.

### `app/services/insight_engine.py`

Generates deterministic insights and KPI objects from actual result data.

Capabilities include:

- row-count insight
- duplicate-row warnings
- outlier warnings
- grouped-analysis summaries
- metric range summaries
- trend change insight
- top comparison insight
- anomaly insight generation
- correlation insight generation
- KPI card generation
- raw fact extraction for reports

### `app/services/result_cache.py`

Defines a file-backed result cache keyed by a fingerprint of:

- execution mode
- intent
- data source
- table name
- schema
- transformations
- analysis settings

This is a reasonable abstraction, but in the current active request path it appears to be instantiated and not actually used.

## Agent layer

### `app/services/agent/classifier.py`

Routes prompts into either:

- `simple`
- `agentic`

It first uses rule-based keyword detection, then falls back to an LLM classifier. Its bias is safety-oriented: if unsure, it tends to classify the prompt as data/agentic work instead of treating it as casual chat.

### `app/services/agent/planner.py`

Creates agent plans and next-step decisions using the LLM. It defines:

- `AgentTask`
- `AgentPlan`
- `NextStepDecision`

It is responsible for deciding what tool should run next.

### `app/services/agent/executor.py`

Implements the Plan -> Execute -> Observe loop. This is the most sophisticated control file in the repository.

Major responsibilities:

- initialize tool registry
- perform initial schema sniffing
- create high-level plan
- repeatedly decide the next step
- sanitize bad LLM tool calls
- enforce hard transition rules
- guard against repetitive loops
- recover from LLM failure
- cache successful tool outputs
- maintain satisfaction and coverage signals
- bind chart generation to the SQL result that produced it
- produce a final synthesis payload

### `app/services/agent/guardrails.py`

Contains `SQLValidator`, which enforces read-only SQL:

- only `SELECT` or `WITH`
- blocks destructive SQL keywords
- auto-adds `LIMIT`
- caps excessive requested limits

This is a central safety control.

## Tool layer

### `app/services/tools/base.py`

Defines the tool abstraction and `ToolResult`.

### `app/services/tools/sql.py`

Runs validated read-only SQL against DuckDB.

### `app/services/tools/schema.py`

Returns schema plus sample rows from DuckDB.

### `app/services/tools/viz.py`

Builds chart configuration objects, not actual chart figures.

### `app/services/tools/reflection.py`

Returns structured reflection objects. This seems more like infrastructure for the agent loop than a user-facing feature.

## LLM layer

### `app/services/llm/client.py`

Provider-aware async LLM client using `httpx`.

Supported providers:

- Groq
- OpenRouter
- Ollama

Behavior:

- chooses providers based on available configuration
- prefers Groq when configured
- can retry with alternate providers if one fails or rate limits
- extracts JSON from model outputs for structured tasks

### `app/services/llm/reasoning.py`

This file contains a broader hybrid reasoning layer with many capabilities:

- schema inference
- user intent classification
- state update suggestion
- primary query interpretation
- plan refinement
- grounded explanation writing
- dynamic insight generation
- SQL generation
- SQL normalization and validation
- canonicalization of interpreted state
- report-section generation

This is one of the richest files in the repository conceptually. However, only parts of it are currently active in the live request path. The most clearly active usage today is:

- dynamic insight generation
- access to the shared LLM client

Other methods appear to belong to a larger architecture direction or earlier implementation iteration.

## Execution layer

### `app/services/execution/pandas_executor.py`

Supports dataframe-based execution for file-backed datasets and also contains:

- a SQLite-in-memory SQL-over-pandas path
- identifier rewriting for SQL
- transformation logic for filters/grouping/time bucketing/sorting/limit
- profile building
- a demo fallback dataset when no real source is attached

### `app/services/execution/sql_executor.py`

Supports direct database querying for live database-backed datasets.

Capabilities:

- build SQL from `QueryState`
- apply filters/grouping/aggregations/sort/limit
- infer dialect from database URL
- execute live SQL through `DatabaseConnector`

### `app/services/execution/unified.py`

Wraps both executors and chooses SQL vs pandas mode depending on source type.

This is a useful abstraction, but it does not appear to be the active runtime path used by `ConversationManager` right now.

## Visualization layer

### `app/services/visualization/chart_resolver.py`

Maps analytical intent to chart types:

- distribution -> histogram
- comparison -> bar
- trend -> line
- relationship -> scatter
- composition -> pie

### `app/services/visualization/plotly_builder.py`

Builds actual Plotly figure payloads from result rows and visualization settings.

Capabilities:

- line charts
- bar charts
- scatter plots
- histograms
- pie charts
- fallback chart generation when axes are weak/missing
- dashboard-style multi-chart generation
- plot payload sanitization for JSON transport
- automatic titles
- prioritization of likely numeric metrics
- top-N trimming for bar charts
- pie chart "Others" grouping

## Persistence layer

### `app/services/data/duckdb_store.py`

Local analytical storage for uploaded file datasets.

Responsibilities:

- keep a persistent DuckDB connection
- ingest pandas dataframes as DuckDB tables
- execute SQL
- inspect schema
- check whether a table exists

### `app/services/persistence/metadata_db.py`

SQLite metadata store for:

- dataset profiles
- query logs

### `app/services/persistence/cache.py`

SQLite-backed persistent cache for tool results keyed by dataset and context.

### `app/services/memory/session_store.py`

JSON-file-backed session store.

Responsibilities:

- create sessions
- cache sessions in memory
- save sessions to disk
- reload sessions from disk
- list prior sessions

## Frontend assets

### `app/web/index.html`

Single-page HTML shell for the built-in MVP interface.

### `app/web/app.js`

All browser-side behavior:

- dataset loading
- session loading
- query submit
- upload flow
- DB registration flow
- rendering chat
- rendering KPIs
- rendering Plotly charts
- rendering insights/warnings
- rendering data preview
- rendering debug info
- toggling dev view
- exporting PDF

### `app/web/styles.css`

Controls the visual design of the browser UI.

## Tests

The `tests/` directory covers:

- API endpoints
- uploads and sessions
- preprocessing
- dashboard/chart generation
- DB connector normalization
- file SQL execution
- insight generation
- database registration
- query history
- LLM reasoning utilities
- optional live PostgreSQL/MySQL integration tests

## Utilities

### `migrate_to_v35.py`

Migration script that moves older dataset metadata into the newer SQLite + DuckDB storage model.

This is a useful signal that the project has gone through architectural evolution rather than being a one-shot prototype.

## 5. Detailed Runtime Flow

## Upload flow

When a user uploads a CSV/Excel file:

1. The browser posts multipart form data to `POST /v1/datasets/upload`.
2. `DatasetService.save_upload()` validates the extension.
3. The file is written to `storage/datasets`.
4. The file is loaded into pandas.
5. `DataPreparationService.prepare()` canonicalizes and profiles the data.
6. A namespaced DuckDB table name is created in the form:
   - `dataset_<id-prefix>_<clean-name>`
7. The prepared dataframe is ingested into DuckDB.
8. A `DatasetProfile` is built with:
   - dataset ID
   - source type
   - file path
   - table name
   - schema
   - label map
   - alias map
   - preprocessing profile
   - row count
9. The dataset profile is saved into SQLite metadata storage.
10. The API returns the dataset profile.

## Database registration flow

When a user registers a database table:

1. The browser posts JSON to `POST /v1/datasets/register-database`.
2. `DatasetService.register_database()` calls `DatabaseConnector.inspect_table()`.
3. The connector validates the URL and inspects the external table.
4. A `DatasetProfile` is created with:
   - dialect
   - database URL
   - table name
   - schema
   - sample rows
   - row count
5. The profile is persisted in SQLite metadata.

Important nuance:

- this registration flow stores metadata for the external table
- it does **not** ingest the live database table into DuckDB

That matters because the active agentic query path is DuckDB-centric.

## Query flow

The active request flow for a BI question looks like this:

1. The UI posts to `POST /v1/query`.
2. `ConversationManager.handle_query()` loads or creates the session.
3. The incoming user message is appended to session history.
4. If `dataset_id` is present, dataset metadata is attached to `QueryState`.
5. `QueryClassifier.classify()` determines whether the prompt is:
   - simple conversational
   - agentic analytical
6. If it is a simple message, `_handle_simple_request()` returns a lightweight response.
7. Otherwise `_handle_agentic_request()` runs the autonomous agent loop.
8. `AgentExecutor.run_agent_loop()`:
   - may sniff schema first
   - asks the planner what tool to run next
   - sanitizes tool decisions
   - executes a tool
   - records observations
   - updates satisfaction/coverage flags
   - repeats up to a max step count
9. The resulting observations are scanned for:
   - SQL results
   - chart configurations
10. Each successful chart config is turned into a Plotly chart payload.
11. A final `QueryResult` is assembled from the final SQL result.
12. `LLMReasoningService.generate_dynamic_insights()` produces narrative insights.
13. `BIResponse` is returned with:
   - explanation
   - insights
   - chart(s)
   - query state
   - execution plan
   - data preview
   - agent steps
   - debug payload
14. The session is saved to disk.

## Session flow

Sessions are central to the product experience.

The system stores:

- session ID
- associated dataset ID
- query state
- messages
- last result
- query history lineage

The UI can:

- list sessions
- switch between sessions
- inspect saved messages and query history

This gives the application a memory model rather than being a pure stateless query API.

## 6. Query State Model

The main conceptual strength of this repository is the explicit `QueryState`.

### `intent`

Represents:

- query type
- user goal
- confidence

Examples of goals implied by the code:

- summary
- comparison
- correlation
- trend analysis

### `data`

Represents:

- source type
- source ID
- active dataset ID
- table name
- available tables
- schema map
- display labels
- alias map
- preprocessing profile

This is the binding layer between natural language and the real dataset.

### `transformation`

Represents:

- filters
- group-by fields
- aggregations
- time granularity
- sort
- limit

This is the structured analytic intent that execution layers can act on.

### `analysis`

Represents requested analytical behaviors such as anomaly detection and its parameters.

### `visualization`

Represents:

- chart type
- x-axis
- y-axis
- color grouping
- title
- display options

### `meta`

Represents runtime and orchestration metadata:

- query IDs
- timestamps
- cached flag
- reasoning notes
- charts
- generated views
- coverage state
- satisfaction state
- loop progress flags
- harvested args
- last SQL result

This is where the autonomous agent stores its self-regulation and memory hints.

## 7. Technologies Used

## Backend

- Python `3.11+`
- FastAPI
- Uvicorn
- Pydantic v2
- pydantic-settings

## Data processing

- pandas
- openpyxl
- DuckDB (used in code for uploaded dataset analytics)
- SQLite
- SQLAlchemy
- psycopg
- PyMySQL

## Visualization

- Plotly

## LLM and external AI providers

- Groq
- OpenRouter
- Ollama
- httpx for provider calls

## Frontend

- plain HTML
- plain CSS
- vanilla JavaScript
- Plotly CDN script
- Marked CDN script for markdown rendering
- Google Fonts

## Testing

- pytest
- FastAPI TestClient

## Packaging / project configuration

- `pyproject.toml`
- setuptools

## 8. Frontend / UI Breakdown

The frontend is intentionally lightweight. It is not a React or Vue app. It is a single static MVP UI served by FastAPI.

### Main UI sections

1. **Sidebar**
   - system status pill
   - active dataset selector
   - upload form
   - connect-database form
   - session selector
   - quick prompt chips

2. **Workspace header**
   - title/subtitle
   - export PDF button
   - dev/debug view toggle

3. **Chat stream**
   - user messages
   - assistant messages
   - state-derived pill metadata attached to the latest assistant message

4. **Results canvas**
   - KPI strip
   - primary chart
   - chart gallery
   - report sections
   - insights and warnings
   - data preview table

5. **Debug drawer**
   - reasoning mode
   - SQL mode
   - matched columns
   - query state JSON
   - execution plan JSON
   - generated SQL
   - executed SQL
   - query history JSON

6. **Sticky composer**
   - textarea input
   - send button
   - loading spinner
   - active dataset pill

### Frontend behavior details

- prevents querying until a dataset is selected
- stores active dataset/session in in-memory browser state
- restores sessions via API
- renders assistant markdown through `marked`
- renders Plotly charts dynamically
- applies a custom dark Plotly theme
- supports browser print/export flow for dashboard output
- exposes internal debugging info for developer visibility

### Frontend significance

This UI matters from a resume/reference perspective because it shows the project is not just backend experimentation. It includes a usable end-to-end interface for:

- data upload
- querying
- charting
- session switching
- debugging

## 9. LLM and Agent Design

This project uses an explicitly hybrid view of intelligence:

- LLM for classification, planning, reasoning, and narrative output
- SQL/pandas for actual data execution

### Query classification

`QueryClassifier` decides whether the prompt is simple or analytical.

It has two notable properties:

1. It uses rule-based keyword detection before LLM routing.
2. It fails safe toward `agentic` mode for ambiguous data-like prompts.

### Planning

`AgentPlanner` creates:

- an initial plan
- a next-step decision after each observation

The planner prompt explicitly instructs the model to:

- fetch data before answering
- use chart generation only after data exists
- avoid repetition
- stop only after the user's request is satisfied

### Tool registry

The agent has these tools:

- `get_schema`
- `run_sql_query`
- `generate_chart`
- `reflect`

This is a classic agent architecture with a constrained toolset instead of open-ended agent freedom.

### Guardrails and recovery logic

The agent executor contains many practical protections:

- schema-first progression
- forced SQL fetch after schema discovery
- loop detection
- anti-repetition controls
- completion overrides when no chart exists for chart/report requests
- chart-context binding
- fuzzy correction of chart axes
- recovery after LLM failure
- cached tool results

This is one of the strongest engineering aspects of the project because it shows deliberate operational hardening rather than naive agent execution.

### LLM provider strategy

The README describes a hybrid mode using:

- Groq for heavier reasoning
- OpenRouter for lighter reasoning

The code also includes Ollama fallback support, which makes the system friendlier for local experimentation.

## 10. Data and Persistence Design

The storage model is local and file-based.

### Data storage locations

Configured roots include:

- `storage/`
- `storage/sessions`
- `storage/datasets`
- `storage/result_cache`

### What gets persisted

1. Uploaded source files
2. DuckDB analytical store
3. SQLite metadata DB
4. SQLite cache DB
5. Session JSON files
6. Optional result cache JSON files

### Why this matters

This design makes the project:

- easy to run locally
- easy to inspect manually
- good for prototyping
- portable without cloud infrastructure

## 11. API Surface

### `GET /`

Serves the browser UI.

### `GET /health`

Returns:

- `{"status":"ok"}`

### `GET /v1/system/status`

Returns runtime flags such as:

- whether LLM mode is enabled
- which provider keys are configured
- selected model names

### `GET /v1/datasets`

Lists registered dataset profiles.

### `POST /v1/datasets/upload`

Uploads a CSV/Excel file and registers it as a dataset.

### `POST /v1/datasets/register-database`

Registers a live database table as a dataset.

### `GET /v1/sessions`

Returns session summaries.

### `GET /v1/sessions/{session_id}`

Returns full session detail including:

- messages
- query state
- query history

### `POST /v1/query`

The main conversational BI endpoint. Returns a rich `BIResponse`.

## 12. Testing Coverage

The test suite shows the intended product surface clearly.

Covered areas include:

- API health and route behavior
- serving the browser UI
- upload -> query -> session flow
- preprocessing and identifier normalization
- chart generation correctness
- database URL normalization
- file-backed SQL execution
- insight generation logic
- LLM reasoning utility behavior
- optional live database integrations

### Important reality check

Some tests appear out of sync with the current implementation. Examples of mismatches visible from static inspection:

- tests refer to helper methods not present in the current `ConversationManager`
- tests assume `data_source`-only requests work end-to-end
- tests assume certain caching/query-history/report behaviors that are not visible in the current active runtime path
- at least one test expects a plain table name where the current dataset ingestion code creates namespaced DuckDB table names

So the test suite is useful as a map of intended behavior, but it should not be treated as a perfect mirror of the live current architecture.

## 13. Major Strengths

### 1. Strong domain modeling

The `QueryState` design is a major architectural strength. It gives the app a consistent internal representation of user intent and analytic context.

### 2. Grounded execution philosophy

The project tries to avoid pure hallucinated BI by grounding analytical work in SQL and dataframe execution.

### 3. Flexible data source onboarding

It supports both uploaded files and database registration, which broadens the product scope.

### 4. Session awareness

The project is multi-turn and session-oriented, which is essential for realistic conversational analytics.

### 5. Built-in UI

The included frontend makes the whole product demonstrable without separate client work.

### 6. Practical agent hardening

The agent executor includes nontrivial safeguards and recovery logic that many prototypes skip.

### 7. Hybrid provider design

The LLM layer is not locked to one provider. It supports multiple remote providers and local fallback ideas.

## 14. Current Gaps, Risks, and Architectural Inconsistencies

This is the section that matters most if you want a truthful LLM reference rather than marketing copy.

### 1. Active runtime path vs available modules are not perfectly aligned

The repository contains:

- a DuckDB-centric agentic path
- a pandas executor
- a SQL executor
- a unified executor
- a larger LLM reasoning framework

But the currently active `ConversationManager` path primarily uses the autonomous agent loop with DuckDB-backed tools and only a subset of the broader abstractions.

### 2. Database registration appears only partially wired into live querying

The app can register external database datasets and inspect them. However:

- registered database tables are not ingested into DuckDB
- the active agent tools query DuckDB
- `ConversationManager` does not appear to use `UnifiedExecutor` or `SQLExecutor` in the current main path

That means the external database path looks architecturally intended, but not fully integrated into the current agentic runtime.

### 3. `data_source` request field appears underused

The API schema includes `data_source`, but the current `ConversationManager` mainly works from `dataset_id`. This suggests an earlier API contract was retained while the main workflow shifted toward registered datasets and sessions.

### 4. Some caching abstractions appear inactive

`ResultCache` exists and is instantiated in `ConversationManager`, but the active code path shown does not visibly consume it.

### 5. Tests appear partially stale

The test suite references some behaviors and helper methods that no longer line up with the current code. This is a maintainability signal.

### 6. DuckDB appears to be an undeclared runtime dependency

The application imports and relies on `duckdb`, but the current `pyproject.toml` dependencies shown do not declare `duckdb`.

That means local environments may work only because DuckDB is already installed elsewhere, such as in the current virtual environment.

### 7. Plain-text persistence of sensitive configuration/data

Potentially sensitive information may be stored locally in plain form:

- `.env` contains provider keys
- session JSON files contain messages and state
- dataset metadata stores database URLs
- database URLs may include credentials

This is acceptable for a local prototype, but it is important to recognize from a security perspective.

### 8. No authentication or authorization layer

The app is designed like a local/internal tool. There is no visible auth layer around dataset management or query endpoints.

### 9. Frontend asset dependence on CDNs

The browser UI pulls:

- Plotly from CDN
- Marked from CDN
- Google Fonts

So the UI is not fully self-contained/offline by default.

## 15. Security and Safety Observations

### Positive safety choices

- AI-generated SQL is intended to be read-only
- SQL guardrails block destructive operations
- query limits are enforced in the validator
- database URL validation is dialect-aware
- tool set is constrained rather than open-ended

### Security concerns

- no auth
- secrets likely stored locally in `.env`
- database URLs persisted in metadata
- session data persisted on disk
- local files and metadata are not encrypted by the app

For a prototype, this is understandable. For production, it would need substantial hardening.

## 16. Resume / Interview Interpretation

If you describe this project professionally, the most accurate framing is:

> Built a conversational BI platform that ingests spreadsheets and database tables, normalizes schema into a canonical analytical state, and answers natural-language questions through a FastAPI backend, autonomous tool-using agent loop, Plotly visualizations, and local session-aware persistence.

Key engineering themes you can honestly claim based on this repository:

- designed a structured query-state engine for conversational analytics
- implemented file ingestion and schema normalization pipelines
- built a local DuckDB-backed analytical execution path
- integrated LLM providers for planning, routing, and insight generation
- created a tool-based autonomous analysis loop with SQL guardrails and recovery logic
- built a browser UI for querying, charting, debugging, and session restoration
- implemented local persistence for datasets, caches, and sessions

## 17. Best Short Summary

`Talking BI v2` is a FastAPI-based conversational analytics system that lets users upload tabular data or register database tables, then ask BI questions in natural language. Internally, it uses a structured `QueryState`, preprocessing/alias mapping, a DuckDB-backed agent tool loop, Plotly chart generation, local session memory, and optional hybrid LLM reasoning through Groq/OpenRouter/Ollama-style providers. The codebase is stronger on architecture and experimentation than on production polish: it has thoughtful state modeling, safety guardrails, and a usable MVP UI, but it also shows evidence of evolving design, partially wired modules, stale tests, and local-prototype security assumptions.

## 18. If You Want to Hand This to Another LLM

Use this framing prompt with the report:

> Read this project reference and help me turn it into resume bullets, interview answers, architecture explanations, or STAR stories. Prefer the active runtime path over legacy/staged modules, and call out architectural strengths as well as current limitations when relevant.

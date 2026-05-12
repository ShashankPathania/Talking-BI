# Talking BI v2

Talking BI v2 is a FastAPI-based conversational business intelligence application for exploring uploaded spreadsheets or registered database tables with natural-language prompts.

The project combines:

- a structured `QueryState` model for multi-turn analytics
- local file and dataset persistence
- DuckDB-backed analysis for uploaded datasets
- Plotly chart generation
- a built-in browser UI
- optional hybrid LLM reasoning for planning, routing, and insight writing

## What it does

Users can:

- upload `CSV` and `Excel` datasets
- register database tables as datasets
- ask BI questions in natural language
- receive explanations, charts, insights, and previews
- continue analysis across saved sessions
- inspect debug state, SQL metadata, and query context in the browser UI

## Tech stack

- Python 3.11+
- FastAPI
- Pydantic v2
- pandas
- DuckDB
- SQLite
- SQLAlchemy
- Plotly
- httpx
- Groq / OpenRouter / Ollama-compatible LLM providers
- plain HTML, CSS, and JavaScript for the built-in frontend

## Quick start

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -e .[dev]
```

### 3. Create a local environment file

```powershell
Copy-Item .env.example .env
```

### 4. Run the app

```powershell
$env:TEMP = "$PWD\_tmp"
$env:TMP = "$PWD\_tmp"
python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to use the built-in UI.

## LLM mode

The project supports a hybrid reasoning mode:

- Groq for heavier reasoning tasks
- OpenRouter for lighter reasoning tasks
- Ollama-compatible local endpoints as an additional fallback option

Execution stays grounded in code:

- SQL is validated as read-only
- pandas and SQL are the real execution layers
- uploaded files are preprocessed into canonical columns and alias maps before reasoning

To enable LLM-backed reasoning, create `.env` from `.env.example` and set keys such as:

- `LLM_ENABLED=true`
- `LLM_MODE=hybrid`
- `GROQ_API_KEY=...`
- `OPENROUTER_API_KEY=...`

You can verify runtime status with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/system/status
```

## Project structure

```text
app/
  api/              FastAPI routes and schemas
  core/             Core state and dataset models
  services/         Conversation, agent, execution, data, LLM, and viz logic
  web/              Built-in browser UI
tests/              Automated tests
ARCHITECTURE.md     Architecture notes
TALKING_BI_V2_PROJECT_REFERENCE.md
                    Detailed project reference / explainer
```

## Helpful docs

- `ARCHITECTURE.md` - high-level architecture notes
- `TALKING_BI_V2_PROJECT_REFERENCE.md` - long-form project explanation useful for resume prep, interviews, or LLM handoff

## Tests

Run the default test suite:

```powershell
$env:TEMP = "$PWD\_tmp"
$env:TMP = "$PWD\_tmp"
python -m pytest -q
```

Optional live database integration tests can be enabled with:

- `TALKING_BI_TEST_POSTGRES_URL`
- `TALKING_BI_TEST_MYSQL_URL`

The live integration tests expect a table named `talking_bi_test_metrics` with numeric columns such as `sales` and `revenue`.

## Notes

- Local runtime data is written under `storage/` and is intentionally excluded from git.
- `.env`, local databases, caches, sessions, and virtual environments are also excluded from git.
- This repository is focused on the application source, tests, and public-facing documentation rather than local working-state files.

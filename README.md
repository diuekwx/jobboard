# j*b development baseline

React application tracker with a FastAPI backend and optional Gmail sync.

## Fresh checkout

Install Python **3.13.7**, Node **22.13.0**, and npm **10.9.2** (npm 11 also supported). `.python-version` and `.nvmrc` record runtime versions. If pyenv has no version selected, run `pyenv install 3.13.7` and `pyenv local 3.13.7`, or use the full path to that Python executable. Do not reuse `backend/venv`; environments contain machine-specific paths.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))"
```

Put those two generated values into `SECRET_KEY` and `SESSION_SECRET_KEY` in `.env`. Keep the default SQLite URL for local development. Copy the example only on a fresh checkout; preserve any existing `.env`.

```powershell
.venv/Scripts/python.exe -m backend.create_tables
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --host localhost --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --host localhost
```

Open http://localhost:5173. Register a local account through `POST /api/user/register` in http://localhost:8000/docs with an email and password, then sign in through the UI. The UI account-creation link is not implemented. Use `localhost` consistently for CORS and authentication cookies. No Google account, LLM, or PostgreSQL server is needed for this flow.

The frontend defaults to API port 8000. To override it, copy `frontend/.env.example` to `frontend/.env`, edit it, and restart Vite. `VITE_*` values are public browser configuration and must never contain secrets.

On macOS/Linux use `python3.13 -m venv .venv`, `.venv/bin/python` instead of `.venv/Scripts/python.exe`, `cp` instead of `Copy-Item`, and `npm` instead of `npm.cmd`. Windows is the verified baseline; other platforms have not yet been tested.

## Verification

No credentials or running services required:

```powershell
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m pytest -q
cd frontend
npm.cmd run verify
```

`verify` runs `typecheck`, `lint`, and `build` in order. Output is `frontend/dist`. Backend tests disable dotenv loading and use in-memory SQLite, fake Gmail, and a stubbed classifier. There is no frontend unit-test suite or configured Python linter yet.

On Windows, stop Vite before reinstalling if npm reports EPERM on a native `.node` file; retry `npm.cmd ci` after it releases the file.

## Optional integrations

For Google sign-in/Gmail, supply your own OAuth web-client credentials in `.env`, register the exact callback URL shown in the example, and enable Gmail API access. Live OAuth requires provider configuration and is not covered by offline verification. Never commit credentials or tokens.

The example sets the LLM budget to zero, which is explicit rules-only mode: deterministic results are stored, with uncertain application records marked for review. To enable local inference, run an OpenAI-compatible endpoint matching `LLM_BASE_URL` and `CLASSIFIER_MODEL`, then raise `GMAIL_LLM_BUDGET_PER_SYNC` (for example, 40). In fallback mode, timeouts, provider failures, malformed output, incomplete batches, and messages over budget remain pending and do not advance the Gmail checkpoint. Sync responses expose non-sensitive request, retry, token, elapsed-time, and pending-reason counts under `classification`. Paid classification remains disabled by default.

## Dependencies and database lifecycle

Install `backend/requirements.txt`, which pins the resolved dependency set. `requirements.in` records dependency intent. For upgrades, resolve that input in a new environment, regenerate exact pins, preserve platform markers, and run verification. The bcrypt pin preserves compatibility with Passlib 1.7.4.

Frontend direct versions and `package-lock.json` are pinned together. Use `npm ci` to install; deliberate upgrades must update both and pass verify.

`create_tables` creates missing tables for a new database, not schema upgrades for existing tables. Never use `--drop` against data you want to keep. Versioned migrations are a separate workstream. See [architecture decisions](docs/architecture.md).

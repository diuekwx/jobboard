# Architecture decisions

Accepted development baseline, 2026-09-05.

## Keep the modular monolith

React 19, TypeScript, React Router, Tailwind 4, and Vite serve the browser UI. `frontend/src/main.tsx` defines login/dashboard routes; `src/api/api.ts` owns the API origin. The unused Vite counter app and logos were removed, as was the unused server-side cookie-parser dependency.

FastAPI routers handle HTTP/authentication, services implement application and sync behavior, and SQLAlchemy models handle persistence. Preserve those boundaries without introducing separate deployments for the baseline.

## Local storage and optional services

SQLite enables local development without a database server and isolated tests. PostgreSQL remains available through DATABASE_URL and psycopg2. SQLite tests do not establish PostgreSQL migration or concurrency correctness. Versioned database migrations are a separate workstream.

Authentication uses JWTs in HTTP-only cookies; Google OAuth uses a signed session cookie. Local HTTP and localhost CORS are development defaults. Setup generates separate signing secrets. Production TLS/cookie settings, encryption, and OAuth hardening remain future work; this is not a production-readiness claim.

Gmail sync fetches and classifies messages, matches applications, persists events, and tracks processed messages. Deterministic rules precede optional LLM fallback. The environment example disables LLM work by default, deferring ambiguous messages until inference is enabled.

## Reproducible verification

Pin runtimes and resolved dependencies, recreate Python environments, and use npm ci. Keep credentials, databases, caches, builds, and local agent tooling out of Git. Tests use in-memory SQLite and fake Gmail, disable dotenv loading, and substitute the LLM client to avoid personal mailbox state and external services.

Backend tests and frontend TypeScript/lint/build form the baseline gate. A startup/register/login smoke test covers runtime dependencies and password hashing that classification tests alone cannot verify. Frontend unit tests and a Python lint policy are not yet implemented.

## Verification record (2026-09-05)

Exported the staged baseline using `git checkout-index` into an ignored clean directory, created an empty Python environment, and installed both dependency sets from their locks:

- Python 3.13.7: pinned install and `pip check` passed.
- Backend: 102 tests passed, including registration, login, and authenticated user lookup.
- Node 22.13.0 / npm 11.6.0: `npm ci`, TypeScript, ESLint, and production build passed. npm 10.9.2 also passed the initial local lint/typecheck.
- Copied the safe environment example, generated local secrets, initialized SQLite, and confirmed API startup.
- The shared working tree also passed 115 tests after concurrent database-foundation changes. Those additional changes are outside this staged baseline.

One upstream Starlette/AnyIO deprecation warning remains; it does not fail verification. Live Google OAuth, Gmail, LLM services, and PostgreSQL were not exercised.

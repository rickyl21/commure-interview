# Project conventions

Full-stack app: React + Vite frontend in `web/`, FastAPI backend in `server/`.
Storage is whatever `PLAN.md` says (in-memory, SQLite, Postgres, ...). Don't assume a specific database.

## Layout
- `server/main.py`: FastAPI routes, all under `/api`
- `server/db.py`: storage setup (connection, schema), if the project uses a database. Keep all storage setup here so the backend can be swapped without touching routes.
- `web/src/api.ts`: the only place that calls `fetch`; use the `api<T>()` helper
- `web/src/App.tsx`: UI
- `PLAN.md`: scope, data model, and API contract. Treat it as the source of truth.

## Rules
- Don't make unnecessary changes without asking first, however, do bring up any potential issues/flaws you notice.
- When I ask a question or talk about planning, do not make code changes. Implementation phase begins when I mention implement or create or make etc...
- Python 3.11+, type hints on every function. TypeScript strict on the frontend.
- Do not add dependencies without asking first.
- Keep it simple: no ORMs, repository layers, or state libraries unless asked.
- Use plain `def` routes, not `async def`, when storage calls are blocking (SQLite, most DB drivers).
- Request bodies are Pydantic models. Raise `HTTPException` for errors; `web/src/api.ts`
  shows the `error` field, falling back to `detail`.
- If a database is used:
  - Parameterized queries only, using the driver's placeholder style. Never build SQL with f-strings.
  - Commit after every write if the driver doesn't autocommit.
  - Enforce uniqueness with a database constraint and handle the violation, rather than check-then-insert.
  - Create the schema idempotently (e.g. `CREATE TABLE IF NOT EXISTS`) so restarts are safe.
- Every UI fetch handles loading and error states.
- Field names must match the API contract in `PLAN.md` exactly on both sides (JSON is snake_case).
- Make small, focused changes. Do one task per request; don't refactor unrelated code.
- If I ask a question ("how would I…", "what are options for…", "how is this so far"), answer it. Don't edit files unless I ask.
- If a request is ambiguous or contradicts PLAN.md, say what you assumed or ask, before changing code.
- After a change, run it (typecheck, tests, or curl the endpoint) and report what you ran and what happened. Say plainly if you couldn't verify something.
- When explaining, give the reasoning and tradeoffs, not just the answer. For design choices, list options and recommend one.
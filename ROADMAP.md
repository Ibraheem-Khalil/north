# NORTH AI Template — Roadmap

This is a production-minded **template/POC**, not a battle-tested product. Below are the concrete improvements planned to harden it.

## Near Term (1–2 days)
- **Testing:** Add unit/integration tests for auth, file processing, orchestrator tool routing (with fake agents), and WebSocket handler smoke tests.
- **Async hardening:** Ensure blocking calls (LLM/Weaviate/Supabase) are offloaded with timeouts/backoff; keep the FastAPI event loop unblocked.
- **Uploads:** Enforce total payload limits and per-request file count/size caps; consider streaming for large files.
- **Docs:** Document env knobs (`ALLOWED_ORIGINS`, `ENABLE_LS_TRACING`, tested Python/LangChain versions) and add a constraints/lock file.

## Medium Term (2–4 days)
- **Frontend structure:** Break the Chat page into smaller components (input area, message list, uploads) and add basic React tests.
- **Lint/format:** Add black/ruff (or equivalent) for the backend and a frontend linter/formatter; wire into CI.
- **Operational checks:** Add a lightweight status script (Supabase/Weaviate/OpenAI ping) and a WebSocket smoke script.
- **Context management:** Add TTL/LRU for per-user contexts; either use or remove unused utilities (e.g., `rate_limiter`).

## Longer Term
- **More agent coverage:** Tests/mocks for Dropbox/Obsidian agents; reliability around external dependencies.
- **Performance:** Cache common metadata, add backoff/retry policies for external calls, and consider streaming/file chunking for very large uploads.
- **Deployment UX:** Provide example env files for common targets (Render, local Docker), and clarify telemetry is opt-in by default.

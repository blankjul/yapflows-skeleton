Two tools for interacting with Yapflows. Choose based on whether you need the server:

- **admin** — Local operations only. No server required. Reads files directly from `$USER_DIR`. Use for reading skill instructions (`admin skills read <name>` renders SKILL.md with env var substitution from `$USER_DIR/.env` and the skill's own `.env`), inspecting env vars, or any task that doesn't touch API state. This is the right tool for skills because it handles env var substitution automatically — do not read SKILL.md manually and reconstruct this.
- **rest** — HTTP API client. Server must be running (default port from `YAPFLOWS_PORT` env var, fallback 8000). Use for anything that reads or modifies server state: sessions, tasks, triggers, agents, settings. Run with no args to discover the full API schema before making calls.

**Decision guide:** Reading a skill's instructions → `admin`. Everything else (creating tasks, browsing sessions, sending API requests) → `rest`. When in doubt, run `rest` with no args first to learn what's available.

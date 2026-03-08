# Yapflows — Framework Reference

Yapflows is a self-hosted personal AI assistant framework. Everything lives in `~/.yapflows/` — no cloud, no database, no data leaves your machine unless you configure it to.

---

## Core concepts

### One conversation, one agent

Every chat session is tied to exactly one agent for its entire lifetime. The agent's provider is baked into its definition — you do not choose it at chat start.

### Providers

| Provider | How it runs | Tools |
|----------|-------------|-------|
| `claude-cli` | `claude` subprocess | Fully autonomous — handles file I/O, web, terminal internally |
| `openrouter` | Strands SDK + OpenRouter API key | Explicit: bash shell, browser |

### Environments

An environment pairs a provider with a specific model. You pick both an agent and an environment when starting a chat. The agent's declared provider must match the environment's provider.

---

## Data directory — `~/.yapflows/`

```
~/.yapflows/
│
├── settings.json               Global settings: providers, integrations, logging
│
├── agents/
│   └── {name}.md               User agent: YAML front matter + system prompt body
│                               Overrides any built-in agent with the same name
│
├── memory/
│   ├── default.md              Auto-loaded in every conversation
│   └── {topic}.md              Topic files — loaded on demand via @mention or by agent
│
├── knowledge/
│   └── {name}.md               Reference documents — loaded on demand via #mention
│
├── chats/
│   └── {session_id}.json       Active chat sessions
│
├── archive/
│   └── {session_id}.json       Archived sessions (read-only in UI)
│
├── tasks/
│   └── {name}.md               Scheduled task: cron + agent + prompt
│
├── runs/
│   └── {id}.json               One record per task execution
│
├── triggers/
│   └── {name}.md               Webhook trigger: agent + prompt template
│
├── skills/
│   └── {name}/
│       ├── skill.md            Description + usage instructions (required)
│       ├── scripts/            Executable scripts the agent calls via bash
│       └── assets/             Templates, data, configs
│
├── environments/
│   └── {id}.json               User environment presets (provider + model)
│
└── log/
    └── YYYY-MM-DD_HHMMSS.log   One log file per server start; oldest pruned on startup
```

---

## File formats

Two formats only:

- **Markdown with YAML front matter** — human-authored definitions (agents, tasks, triggers)
- **JSON** — machine-generated records (sessions, runs, environments, settings)

### Agent file — `~/.yapflows/agents/{name}.md`

```markdown
---
name: My Assistant
provider: claude-cli
model: claude-opus-4-5
color: "#6366f1"
---

You are a personal assistant...
```

Required front matter: `provider`, `model`. The body (after `---`) is the system prompt — front matter is stripped before it reaches the model.

### Task file — `~/.yapflows/tasks/{name}.md`

```markdown
---
cron: "0 9 * * 1-5"
agent: assistant
model: ""
enabled: true
sticky_session: false
---

Generate my daily standup report...
```

### Trigger file — `~/.yapflows/triggers/{name}.md`

```markdown
---
agent: assistant
model: ""
---

A message arrived: {{payload}}

Reply to the sender directly.
```

`{{payload}}` is replaced with the incoming request body when the trigger fires.

### Environment file — `~/.yapflows/environments/{id}.json`

```json
{
  "id": "my-haiku",
  "name": "Haiku (fast)",
  "provider_id": "openrouter",
  "model": "anthropic/claude-haiku-4-5"
}
```

### Settings file — `~/.yapflows/settings.json`

Key fields:

| Path | Description |
|------|-------------|
| `providers.openrouter.api_key` | OpenRouter API key |
| `integrations.telegram.bot_token` | Telegram bot token |
| `integrations.telegram.chats` | List of allowed Telegram chat configs |
| `logging.level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `logging.keep` | Number of log files to retain (default 30) |
| `heartbeat` | Heartbeat scheduler config (enabled, cron, agent, prompt) |

---

## Memory

`default.md` is injected into the system prompt at the start of every conversation — keep it short (core facts about you, preferences, timezone).

Topic files (`~/.yapflows/memory/{topic}.md`) are loaded on demand:
- Type `@topic` in the chat composer to attach it for one turn
- The agent loads topic files via bash when it decides they are relevant

The agent reads and writes memory as plain files via bash — no special memory API.

---

## Knowledge

Reference documents for subjects and topics (not personal context). Loaded on demand only:
- Type `#name` in the chat composer to attach a document for one turn

The agent can also read/write knowledge files via bash.

**Memory vs. Knowledge:**

| | Memory | Knowledge |
|-|--------|-----------|
| What | Things about *you* | Reference docs on topics |
| Auto-loaded | `default.md` only | Never |
| Size | Small, concise | Arbitrary |

---

## Sessions

Sessions are created by:
- **Manual** — you click New Chat
- **Scheduled** — a task fires on cron
- **Trigger** — a Telegram message or webhook arrives

**Sticky sessions** are pinned at the top of the list and never auto-archived. A task with `sticky_session: true` reuses one session across all its runs.

The session title is auto-set from the first user message (~60 chars). You can rename it by double-clicking.

---

## Skills

Skills are reusable capabilities packaged as directories. The agent discovers available skills from its system prompt, reads `skill.md` to understand the interface, and invokes scripts via bash.

User skills at `~/.yapflows/skills/{name}/` override any built-in skill with the same name.

Minimum structure:
```
~/.yapflows/skills/my-skill/
├── skill.md          (required)
└── scripts/
    └── run.sh
```

There is no "create skill" button in the UI — create and edit skill directories directly on disk.

---

## Tasks and scheduling

Tasks fire on cron schedules and create a chat session per run. Run records are written to `~/.yapflows/runs/{id}.json`.

Cron format — `minute hour day-of-month month day-of-week`:

| Expression | Meaning |
|-----------|---------|
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 8 * * 1` | Every Monday at 8:00 AM |
| `*/30 * * * *` | Every 30 minutes |

Runs are processed one at a time through a single background queue. "Run now" places a run at the back of the queue.

---

## Triggers

**Telegram** — configure bot token and allowed chat IDs in Settings. Each Telegram chat maps to one sticky session. The agent's reply is sent back via the Telegram API.

**Webhooks** — POST to `/api/triggers/{name}`. Define the trigger file at `~/.yapflows/triggers/{name}.md`. No UI management — create files directly.

---

## System prompt assembly

On each conversation turn, the full system prompt is assembled as:

```
{agent body}
---
{~/.yapflows/memory/default.md, if it exists}
---
{Framework instructions: memory conventions, knowledge conventions, available skills}
```

Only `default.md` is injected automatically. Topic files and knowledge documents are loaded explicitly.

---

## Built-in defaults

Built-in agents, environments, and skills live in the project's `defaults/` directory (or `backend/` depending on install). User files always take precedence over built-ins with the same identifier.

---

## Backup

Backup = copy `~/.yapflows/`. All sessions, memory, tasks, and settings are human-readable files. No migration or schema management needed.

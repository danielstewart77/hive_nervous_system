# hive_nervous_system

Containerized vector store + knowledge graph (lucent) shared across every mind in the [Hive Mind](https://github.com/danielstewart77/hive_mind) ecosystem.

This is the **data plane** — minds (Ada, Bob, Bilby, Nagatha, Skippy) hold no lucent code. They reach this service over HTTP with a bearer token. One database, many writers, provenance recorded per write but no `mind_id` filter on reads (every mind sees everything).

## What's in here

- **`lucent_api/`** — FastAPI app with two routers: `/memory/*` (vector store) and `/graph/*` (knowledge graph). Bearer-gated on every route except `/health`.
- **`core/`** — pure Python: data class registry, four-class pruner (`prune-memory`), shared Telegram notifier, secrets adapter.
- **`server.py`** — container entry. Starts uvicorn + an APScheduler in-process cron (`prune-memory` daily at 4am).
- **`Dockerfile`, `docker-compose.yml`** — single-container deployment, joined onto the external `hivemind` Docker network so other minds reach it as `hive-lucent:8424`.
- **`scripts/migrations/`** — one-shot DB migrations (archived after run).

## Quick start

```bash
# 1. Set a bearer token
cp .env.example .env
echo "LUCENT_BEARER_TOKEN=$(openssl rand -base64 32)" > .env

# 2. Make sure the external `hivemind` docker network exists
docker network create hivemind 2>/dev/null || true

# 3. Bring it up
docker compose up -d --build

# 4. Health check
curl http://127.0.0.1:8425/health
# {"status":"ok","service":"lucent-api"}
```

## Endpoints

All bearer-gated except `/health`.

| Path | Purpose |
|---|---|
| `GET /health` | open — `{"status":"ok","service":"lucent-api"}` |
| `GET /memory/list?tier=<t>&offset=<n>&limit=<n>` | list entries; optional `tier=` server-side filter |
| `GET /memory/retrieve?query=<q>&data_class=<c>&k=<n>&min_score=<s>` | semantic search |
| `GET /memory/recent-decayed?limit=<n>` | top-N by recency-decay score |
| `POST /memory/store` | write — body `{content, data_class, tier, mind_id, source}` |
| `PUT /memory/{id}` | update content / data_class / tags |
| `DELETE /memory/{id}` | delete |
| `GET /graph/query?entity_name=<name>&mind_id=<id>&depth=<n>` | identity lookup |
| `GET /graph/search?text=<q>&limit=<n>` | mention search |
| `GET /graph/raw-properties?name=<n>&mind_id=<a>` | unflattened properties blob (round-trip safe) |
| `GET /graph/data?limit=<n>` | visualization export — flat nodes + edges |
| `POST /graph/upsert` | write node + optional edge (with orphan/disambiguation guards) |
| `POST /graph/upsert-direct` | write node directly (skips orphan/disambiguation guards; identity guard still applies) |

## Identity convention

Every write must populate `mind_id` with the **canonical mind id** — for registry-managed minds this is a UUID issued by the consuming mind's session manager. Hardcoding short names (`"ada"`, `"bob"`) creates parallel identities that diverge from the registry. The schema column is `TEXT`; the database does not enforce the rule. See the consuming side's docs.

## Bearer auth

`LUCENT_BEARER_TOKEN` env var on the container. Empty value = bypass mode with a startup warning (deployment safety so a fresh container doesn't lock the operator out before the token is set). Once set, validation is enforced; unauthenticated requests get 401.

## Documentation

The full design, implementation playbook, and verifiable requirements live under [`docs/`](./docs):

- **[Design](./docs/memory-system-design.md)** — mind-agnostic architecture: rotation, four-layer bootstrap, capture pipeline, pruning, graph query semantics. Read this first.
- **[Implementation](./docs/memory-system-implementation.md)** — adopter playbook. How a mind plugs into the shared service: env, identity convention, hooks per harness, verification checklist, "Constraints (don't relearn)".
- **[Requirements](./docs/memory-system-requirements.md)** — 84 verifiable requirements across 15 sections, each with a verification method.
- **[Session prompt composition](./docs/session-prompt-composition.md)** — what `comms/bootstrap_loader.py::compose_prompt_blocks` builds (soul + standing + decay-weighted recent + session-memory carry-forward), the dispatch payload contract, and how the composed string is shipped to each mind's harness.

## Pruning

APScheduler in-process, default `0 4 * * * America/Chicago`. Override via `PRUNE_CRON` and `PRUNE_TIMEZONE`. Per-class strategies live in `core/prune_memory.py`:

- `prune_ephemeral()` — no-op.
- `prune_current_state()` — anchor priority: `codebase_ref` → `expires_at` → `kg_entity` → decay (180d half-life, 0.02 threshold).
- `prune_future_state()` — Ollama shipped-check, then decay (90d).
- `prune_feedback()` — decay only (90d). Standing-tier exempt.

Run output is appended as JSONL to `/data/prune.log` inside the container.

## Schema

```sql
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mind_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,
    tags TEXT,
    source TEXT NOT NULL,
    data_class TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'contextual',
    as_of TEXT,
    expires_at TEXT,
    superseded INTEGER DEFAULT 0,
    recurring INTEGER DEFAULT 0,
    codebase_ref TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mind_id TEXT NOT NULL,
    type TEXT NOT NULL,             -- 'Mind' for identity nodes
    name TEXT NOT NULL,
    first_name TEXT, last_name TEXT,
    properties TEXT DEFAULT '{}',
    data_class TEXT, tier TEXT, source TEXT,
    as_of TEXT, created_at REAL, updated_at REAL,
    UNIQUE(mind_id, name)
);

CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mind_id TEXT, source_id INTEGER, target_id INTEGER,
    type TEXT, as_of TEXT, source TEXT,
    data_class TEXT, tier TEXT, created_at REAL
);
```

## License

MIT.

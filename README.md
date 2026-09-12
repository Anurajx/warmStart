# Warmstart — an AI cost & latency firewall

A production-styled demo that puts a **Redis vector cache in front of an LLM
provider**. Every incoming AI request is checked against a fast three-layer
pipeline before any money is spent on inference:

1. **Layer 1 — Exact-match** (Redis `HGET`, single-digit-ms): same
   user/tenant + model + prompt version + composite request context hits a hash
   key (`warmstart:exact:{version}:{namespace}:{sha256}`).
2. **Layer 2 — Semantic-match** (redisvl + Redis Stack vector search): a
   paraphrase of a previously answered query is found with cosine similarity
   above a configurable threshold.
3. **Layer 3 — Provider fallback**: only a miss calls the real LLM, and the
   fresh result is persisted into both cache layers.

The system is privacy-conscious by design: caching is **per-tenant
(namespaced)**, cost accounting is **per-customer-tier** (Free / Gold), and a
prompt-version **deployment key** means shipping a new system prompt (or
retiring `tools`) immediately orphans stale entries. An interactive
**Next.js dashboard** demonstrates live latency/cost deltas between the direct
provider path and the warmed path, and an **LLM-as-a-judge** background hook
guards semantic-hit quality (false-hit detection surfaced on the metrics).

---

## Architecture

```
┌────────────┐          ┌──────────────────────┐         ┌─────────────┐
│  Next.js   │  /api/*  │   FastAPI (backend)  │  Redis  │ Redis Stack │
│  dashboard │ ───────► │  warmstart firewall  │ ──────► │  · exact L1 │
│  :3000     │  rewrite │        :8000         │ keys    │  · vector L2│
└────────────┘          └──────────────────────┘         └─────────────┘
                              │  │
                     OpenAI ──┘  └── judge hook (LLM-as-a-judge)
```

- `backend/app/config.py` — settings (env prefix `WARMSTART_`), pricing, thresholds.
- `backend/app/cache_engine.py` — the 3-layer pipeline, key builder, metrics ledger, cache busting.
- `backend/app/evaluator.py` — asynchronous LLM judge for semantic-hit quality.
- `backend/app/main.py` — API surface + aggregated `/api/metrics`.
- `frontend/` — Next.js 15 live dashboard (comparative pipeline view, audit stream, admin bust).

### Redis key layout

| Purpose        | Key pattern                                                              |
| -------------- | ------------------------------------------------------------------------ |
| Exact cache    | `warmstart:exact:{version}:{namespace}:{sha256}`                          |
| Vector cache   | `warmstart:vec:{version}:{namespace}:{docid}` (index prefix `warmstart:vec:`) |
| Metrics ledger | `warmstart:metrics` (hash)                                                 |
| Audit hits     | `warmstart:audit:{version}:{namespace}` (list)                             |

All caching is tenant-scoped: `namespace = sha256(user_id)[:12] + "-" +
composite_hash(model, version, tools, tier)`, so a cached answer can never leak
across users, and changing the prompt version, tool set, model or tier instantly
isolates the request into a fresh namespace.

---

## Quick start (Docker)

You need Docker with an `OPENAI_API_KEY` in `backend/.env` (copy from
`backend/.env.example`).

```bash
docker compose up --build
```

| Service  | URL                    |
| -------- | ---------------------- |
| Dashboard| http://localhost:3000  |
| OpenAPI  | http://localhost:8000/docs |
| Health   | http://localhost:8000/api/health |

## Quick start (local dev)

Prereqs: Redis Stack on `localhost:6379` (vector capability), Python 3.12+,
Node 20+.

```bash
# 1. backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # add OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000

# 2. frontend (separate terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

`npm run dev` rewrites `/api/*` to `http://localhost:8000` automatically.

## Offline test suite

The pipeline is unit-tested **without any network calls** — fakeredis plus stubbed
OpenAI and vectorizer:

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/test_pipeline.py -q        # or: python tests/test_pipeline.py
```

Covers exact-hit, semantic-hit, below-threshold miss, cross-tenant isolation,
cache busting by version, metrics accounting, and raw-path no-cache guarantees.

---

## API surface

| Method | Path                          | Purpose                                        |
| ------ | ----------------------------- | ---------------------------------------------- |
| POST   | `/api/query/raw`              | Direct provider call (control path, no cache)  |
| POST   | `/api/query/warmstart`        | Firewall pipeline (exact → vector → provider)  |
| POST   | `/api/admin/bust-cache`       | Purge all keys for one system-prompt version   |
| GET    | `/api/metrics`                | Aggregated hit/cost/latency/false-hit metrics  |
| GET    | `/api/health`                 | Redis + LLM connectivity + build version       |

### Config knobs (`WARMSTART_*`)

| Variable                          | Default      | Meaning                                   |
| --------------------------------- | ------------ | ----------------------------------------- |
| `WARMSTART_OPENAI_API_KEY`        | —            | Provider + judge auth (falls back to `OPENAI_API_KEY`) |
| `WARMSTART_MODEL`                 | `gpt-4o-mini`| Provider model                             |
| `WARMSTART_SEMANTIC_THRESHOLD`    | `0.78`       | Cosine threshold for vector hits           |
| `WARMSTART_CACHE_TTL_SECONDS`     | `86400`      | Cache entry lifetime                       |
| `WARMSTART_ENABLE_LLM_JUDGE`      | `true`       | Background false-hit evaluation            |

> Demo note: the `Bust Cache · Deploy v2.0` button in the dashboard invalidates
> the `v1.0` namespace and switches the console to `v2.0`, simulating a system
> prompt release.
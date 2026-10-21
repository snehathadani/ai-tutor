# AI Tutor

A real-time multi-tutor voice AI built with LiveKit, FastAPI, Redis, and React.
Each tutor is defined by `tutors/<id>/tutor.yaml` and an optional
`tutors/<id>/problems.yaml`. The worker is dispatched with explicit tutor
metadata so session ids and mastery are namespaced per tutor.

**Verified environment:** backend requirements resolve and install on Python 3.11 (native
conda dev) and Python 3.12 (`python:3.12-slim` Docker base). The compose stack was validated
with `podman-compose` 1.0.6 because Docker is not installed on the build machine; the
`docker-compose.yml` is standard syntax and should behave identically under real Docker.

## Architecture

```
┌─────────────┐      WebSocket      ┌──────────────────────┐
│   Browser   │◄───────────────────►│  LiveKit Cloud       │
│  (React)    │                     │  (rooms + inference) │
└────┬────────┘                     └──────────┬───────────┘
     │                                         │
     │ HTTP  /api/token, /api/mastery          │ dispatches jobs
     │                                         │  {tutor_id: ...}
     ▼                                         ▼
┌─────────────┐                         ┌──────────────┐
│  FastAPI    │                         │ livekit-agent│
│  (read-only)│                         │ worker       │
└────┬────────┘                         └──────┬───────┘
     │                                          │
     │ reads                                    │ writes
     ▼                                          ▼
┌─────────────────────────────────────────────────────┐
│                     Redis 7                          │
│  tutor:{id}:mastery, tutor:{id}:sessions,           │
│  tutor:{id}:session:{sid}:...                       │
└─────────────────────────────────────────────────────┘
```

- **frontend** — Vite + React + TypeScript, dark-only UI. Talks to LiveKit for media and to the API for tokens/history. Nginx proxies `/api` in Docker; Vite dev server proxies it locally.
- **api** — FastAPI/uvicorn. Stateless. Mints LiveKit JWTs and serves read-only tutor/mastery/session views.
- **agent** — `livekit-agents` worker that joins a room, runs VAD→STT→LLM→TTS, persists transcript/mastery/summary to Redis.
- **redis** — Sole conversation state store; AOF enabled in compose.

Key invariant: only the agent writes Redis conversation state. The API is read-only.

## Tutor content

Tutors live under `tutors/<id>/`:

```
tutors/
└── probability/
    ├── tutor.yaml      # metadata, persona, concepts, references
    └── problems.yaml   # optional problem bank
```

- `tutor.yaml` — `title`, `subject`, `description`, optional `age_range`, required `persona` (system instructions), optional `level_labels`, and `concepts` with optional `references`. There is no `id` field: the tutor id comes from the directory name (`tutors.py` overwrites any `id` key in the YAML with it).
- `problems.yaml` — optional `problems` list; a missing file means the tutor can converse but has no problems to serve.
- The directory name must equal the tutor `id`.
- References are UI-only: the agent persona never contains URLs and the agent never speaks a URL. The reference URLs shipped with the probability tutor are examples only — a tutor author should replace them with links they have verified.

The registry validates tutors on load, excludes invalid ones with a logged error, and exposes them on `GET /api/tutors` in the `invalid` array (the tutor picker shows a warning row for them). `GET /api/tutors` also returns each tutor's `concepts` — including each concept's `references` — and its `level_labels`, so the picker, link card, and mastery panel render without a second fetch; `GET /api/tutors/{id}` returns the full tutor. Set `TUTORS_DIR` to point at the content directory.

## LLM provider configuration

The tutor is provider-neutral. Set four env vars and swap models without touching code.

| Variable | Values | Notes |
|----------|--------|-------|
| `LLM_PROVIDER` | `openai` (default), `anthropic` | Any other value fails at startup with a clear error. |
| `LLM_BASE_URL` | e.g. `https://api.openai.com/v1`, `https://api.deepseek.com`, `https://api.anthropic.com` | Any OpenAI-compatible gateway works for `openai`. The Anthropic plugin also honours `base_url`. |
| `LLM_API_KEY` | your key | For the chosen provider. |
| `LLM_MODEL` | plain string | e.g. `gpt-4o-mini`, `deepseek-chat`, `claude-sonnet-4-5`. Passed through verbatim. |

### Swap the model without touching code

```bash
# OpenAI
LLM_PROVIDER=openai LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini

# DeepSeek via the OpenAI-compatible plugin
LLM_PROVIDER=openai LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-chat

# Anthropic
LLM_PROVIDER=anthropic LLM_BASE_URL=https://api.anthropic.com LLM_MODEL=claude-sonnet-4-5
```

Unknown `LLM_PROVIDER` values, or missing `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`, cause a clear startup error from the worker preflight and exit with code 1.

## Key decisions and tradeoffs

1. **LiveKit Inference for STT/TTS** — Uses only `LIVEKIT_API_KEY`, so no extra Deepgram/Cartesia accounts are needed. Verified model ids from `livekit-agents` 1.8.8's inference registry:
   - STT: `deepgram/nova-3` (current documented default)
   - TTS: `cartesia/sonic-3.5` with Cartesia's "Ellie" default voice id `79a125e8-cd45-4c13-8a67-188112f4dd22`
   
   Tradeoff: requires a LiveKit Cloud project and incurs Cloud inference usage.
2. **Provider-neutral LLM wiring** — `livekit-plugins-openai` handles any OpenAI-compatible endpoint; `livekit-plugins-anthropic` handles Anthropic. The model string is passed verbatim, so new providers/models work by changing env vars. Tradeoff: we rely on each plugin's compatibility with the target API.
3. **Redis as the only state store** — Keeps the API stateless and makes the agent the single writer. Tradeoff: Redis becomes a single point of availability; if it is down the API still serves health but returns 503 for state reads.
4. **Deterministic mastery in code** — The LLM can only call tools; actual level/streak math lives in `lib/state.py`. This prevents the model from hallucinating progress.
5. **Socratic system prompt** — The agent is instructed to hint and ask leading questions, never to blurt the final answer when the student should reason.
6. **No auth** — Acceptable for a take-home demo. Anyone with the URL can join.

## Scaling to 10,000 concurrent sessions

Today: one agent container and one API process handle one session per room in one worker. To reach 10,000 concurrent sessions:

- Run **many agent workers** behind LiveKit's dispatch layer (the worker registers with LiveKit; LiveKit assigns jobs). Workers are horizontally scalable and share Redis.
- Run multiple **API replicas** behind a load balancer; they are stateless.
- Use a **managed Redis cluster** (e.g., ElastiCache/Redis Cluster) with replication and persistence. Shard by user/session if needed.
- Add a **rate limiter** on `/api/token` and per-room participant limits to prevent abuse.
- Offload long-running summaries to a background worker queue instead of doing it inline on disconnect.
- For 10k simultaneous audio streams, consider region-aware LiveKit Cloud routing and autoscaling agents by CPU/memory.

## How to run

Two run paths; the compose file itself is standard `docker-compose.yml` syntax, so Docker users are unaffected by anything below.

### Docker (grader path)

```bash
cp .env.example .env
# fill in LIVEKIT_*, LLM_*, etc.
docker compose up --build
```

### Podman (dev path on this machine)

```bash
./scripts/dev-up.sh
```

The script exists because `podman-compose` 1.0.6 does not recreate containers on a plain
`up -d --build`: it errors on the already-taken container names, falls back to `podman start`, and
keeps serving the stale image after a rebuild. It therefore runs `down --remove-orphans` first and
then `up -d --build --force-recreate`, so the freshly built image is always what actually serves.

The frontend is on http://localhost:3000, API on http://localhost:8000/api.

Redis is **not** published to the host anymore; the api and agent reach it on the internal compose
network. If you run native dev with a host Redis, bind it to a non-default port (e.g. `6380`) to
avoid colliding with other services.

### Native dev

Backend (Python 3.11 conda env used for validation; adjust for your own venv):

```bash
cd backend
/home/rohit/miniconda3/envs/llm/bin/python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env  # fill it in
# Point TUTORS_DIR at the repo-root tutors directory when running from backend/.
TUTORS_DIR=../tutors python -m uvicorn api.main:app --reload --port 8000
```

If your local Redis is on a different host port, set e.g. `REDIS_URL=redis://127.0.0.1:6380/0`. The default `TUTORS_DIR=./tutors` in `.env.example` works when running from the repo root; from `backend/` use `TUTORS_DIR=../tutors`.

Agent (in another shell):

```bash
cd backend
source .venv/bin/activate
python -m agent.worker
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Tests:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. python -m pytest tests -v
```

## Agent dispatch

The worker registers with the explicit `agent_name` `tutor` (`backend/agent/worker.py`).
Every time `/api/token` mints a LiveKit JWT, the API also requests an explicit agent
dispatch for that room via LiveKit's `agent_dispatch.create_dispatch`
(`backend/api/main.py`). The dispatch metadata is JSON `{"tutor_id": ...}`; the worker
reads `ctx.job.metadata` to resolve the tutor at job start. Verified against
`livekit-agents` 1.8.8.

This means the worker does **not** need to be running before the participant joins. If the worker is down when a token is minted, the dispatch is still created; the frontend joins the room, waits up to ~20 seconds for an agent participant, and then shows a "Retry" button so the user can request another dispatch once the worker is available.

## Redis key reset

Mastery and sessions are now namespaced per tutor:

- `tutor:{tutor_id}:mastery`
- `tutor:{tutor_id}:sessions`
- `tutor:{tutor_id}:session:{sid}:transcript`
- `tutor:{tutor_id}:session:{sid}:meta`
- `tutor:{tutor_id}:session:{sid}:summary`
- `tutor:{tutor_id}:session:{sid}:chat_ctx`

The old global `tutor:user:mastery` / `tutor:user:sessions` / `tutor:session:{sid}:...`
keys from earlier versions are no longer read or written. There is no migration shim;
deployments using the old keys will start with empty per-tutor state.

## What is untested

- Real LiveKit Cloud audio rooms (no valid production credentials were available).
- Actual provider voice responses (LLM calls require a real `LLM_API_KEY`).
- Docker itself; only `podman-compose` was available for compose validation.

## Security note

There is no authentication. The API mints tokens for any requested room and identity. This is intentional for a demo but must be replaced with proper user/session auth before any real deployment.

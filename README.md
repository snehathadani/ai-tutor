# Probability Voice Tutor

A real-time voice AI tutor for 12-year-olds learning probability, built with LiveKit,
FastAPI, Redis, and React.

**Verified environment:** backend requirements resolve and install on Python 3.11 (native
conda dev) and Python 3.12 (`python:3.12-slim` Docker base). The compose stack was validated
with `podman-compose` 1.0.6 because Docker is not installed on the build machine; the
`docker-compose.yml` is standard syntax and should behave identically under real Docker.

## Architecture

```
┌─────────────┐      WebSocket      ┌──────────────────────┐
│   Browser   │◄───────────────────►│  LiveKit Cloud       │
│  (React)    │                     │  (rooms + inference) │
└──────┬──────┘                     └──────────┬───────────┘
       │                                        │
       │ HTTP  /api/token, /api/mastery         │ dispatches jobs
       ▼                                        ▼
┌─────────────┐                         ┌──────────────┐
│  FastAPI    │                         │ livekit-agent│
│  (read-only)│                         │ worker       │
└──────┬──────┘                         └──────┬───────┘
       │                                        │
       │ reads                                    │ writes
       ▼                                        ▼
┌─────────────────────────────────────────────────────┐
│                     Redis 7                          │
│  mastery, transcript, meta, summary, chat context   │
└─────────────────────────────────────────────────────┘
```

- **frontend** — Vite + React + TypeScript, dark-only UI. Talks to LiveKit for media and to the API for tokens/history. Nginx proxies `/api` in Docker; Vite dev server proxies it locally.
- **api** — FastAPI/uvicorn. Stateless. Mints LiveKit JWTs and serves read-only mastery/session views.
- **agent** — `livekit-agents` worker that joins a room, runs VAD→STT→LLM→TTS, persists transcript/mastery/summary to Redis.
- **redis** — Sole conversation state store; AOF enabled in compose.

Key invariant: only the agent writes Redis conversation state. The API is read-only.

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

### Docker / podman compose (production-like)

```bash
cp .env.example .env
# fill in LIVEKIT_*, LLM_*, etc.
docker compose up --build
```

The frontend is on http://localhost:3000, API on http://localhost:8000/api.

> I verified the compose stack locally with `podman-compose` 1.0.6 because Docker was not installed on the build machine. The file is standard `docker-compose.yml`, so real Docker should produce the same result. Redis is **not** published to the host anymore; the api and agent reach it on the internal compose network. If you run native dev with a host Redis, bind it to a non-default port (e.g. `6380`) to avoid colliding with other services.

### Native dev

Backend (Python 3.11 conda env used for validation; adjust for your own venv):

```bash
cd backend
/home/rohit/miniconda3/envs/llm/bin/python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env  # fill it in
python -m uvicorn api.main:app --reload --port 8000
```

If your local Redis is on a different host port, set e.g. `REDIS_URL=redis://127.0.0.1:6380/0`.

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

The worker is registered **without an explicit `agent_name`** (`backend/agent/worker.py`). Verified against `livekit-agents` 1.8.8: an unnamed worker accepts any room job LiveKit offers, so every room the frontend joins gets an agent automatically.

Failure mode: the worker must be running **before** the participant joins the room. If the worker starts after the join, LiveKit will have no available worker to dispatch and the room will have no agent. For a multi-agent deployment you would instead register named workers and create explicit dispatches from the API.

## What is untested

- Real LiveKit Cloud audio rooms (no valid production credentials were available).
- Actual provider voice responses (LLM calls require a real `LLM_API_KEY`).
- Docker itself; only `podman-compose` was available for compose validation.

## Security note

There is no authentication. The API mints tokens for any requested room and identity. This is intentional for a demo but must be replaced with proper user/session auth before any real deployment.

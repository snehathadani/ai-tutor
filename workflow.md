# My workflow for this project

I used a small agent pipeline to design, implement, and validate the project.

## Design phase

- **AI tool**: `pi-subagents` with `failover/deepseek-v4-pro` (sonnet class).
- **Task**: I fed the assignment and a quick code recon into the `oracle` subagent and asked for a concrete architecture: service split, Redis schema, API surface, file tree, curriculum, and build order.
- **Outcome**: `/tmp/ai-tutor-design.md`. It locked the stack (FastAPI + livekit-agents + Redis + React), the Redis key schema, the Socratic voice loop, and the agent/tools split.

## Implementation phase

- **AI tool**: `pi-subagents` `worker` with `failover/kimi-k2.7-code` (coding class).
- **Task**: Implement the approved design file-by-file. I did not write code in the parent loop; the `worker` made all edits and ran validation.
- **Key adaptation**: the installed `livekit-agents` 1.8.8 API uses `AgentServer` + `@server.rtc_session` and `AgentSession.start(agent=..., room=...)` instead of the older `WorkerOptions`/`cli.run_app` pattern. I introspected the package (`dir()`, `inspect.signature`) and adapted the worker and session setup accordingly.

## Validation loop

I ran checks continuously instead of writing a large block and hoping:

1. `python -m pytest tests` for the FastAPI token endpoint and Redis state layer (using `fakeredis`).
2. `npx tsc --noEmit && npm run build` for the frontend.
3. `podman-compose up -d --build` and `curl` against the published API/frontend ports.
4. `podman-compose run --rm agent` with empty credentials to confirm a clean error message.

Where a check failed, I fixed the narrow issue and re-ran the same command before moving on.

## AI assistance style

- I used the models for **code skeleton, API introspection, and error diagnosis**, but I verified every external API call against the actual installed package.
- I kept the design document as the contract and did not let the implementation widen scope (no extra auth, no extra models, no mock voice demo).
- Human-in-the-loop happened only when a real decision was needed (none here; the approved plan was complete).

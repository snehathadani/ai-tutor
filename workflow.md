# My workflow for this project

I used a small agent pipeline to design, implement, and validate the project.

## Design phase

- **AI tool**: `pi-subagents` with `failover/deepseek-v4-pro` (sonnet class).
- **Task**: I fed the assignment and a quick code recon into the `oracle` subagent and asked for a concrete architecture: service split, Redis schema, API surface, file tree, curriculum, and build order.
- **Outcome**: `/tmp/ai-tutor-design.md`. It locked the stack (FastAPI + livekit-agents + Redis + React), the Redis key schema, the Socratic voice loop, and the agent/tools split.

## Implementation phase

- **AI tool**: `pi-subagents` `worker` with `failover/kimi-k2.7-code` (coding class).
- **Task**: Implement the approved design file-by-file. I did not write code in the parent loop; the `worker` made all edits and ran validation.
- **Multi-tutor externalization**: after the single-tutor version worked, a new design pass (`oracle`, `failover/deepseek-v4-pro`) externalized tutors into `tutors/<id>/tutor.yaml` plus optional `problems.yaml`. The `worker` then implemented `TutorRegistry` (`backend/lib/tutors.py`): validates each tutor, excludes invalid ones with a logged warning while valid tutors still load, hot-reloads on file changes keyed on `(mtime_ns, size)`, and reports invalid tutors on `GET /api/tutors`. It also namespaced Redis keys per tutor (`tutor:{tutor_id}:...`) and switched dispatch to explicit agent dispatch with `{"tutor_id": ...}` metadata, so session ids and mastery never collide across tutors.
- **Key adaptation**: the installed `livekit-agents` 1.8.8 API registers handlers with the method form `server.rtc_session(entrypoint, agent_name=..., on_session_end=...)` on an `AgentServer` instance (`backend/agent/worker.py`), plus `AgentSession.start(agent=..., room=...)`, instead of the older `WorkerOptions`/`cli.run_app` pattern. I introspected the package (`dir()`, `inspect.signature`) and adapted the worker and session setup accordingly.

## Review rounds

Every implementation pass was followed by three parallel reviewers (correctness, tests, simplicity/style) on `failover/deepseek-v4-pro`; their findings went back to `worker` as a focused fix round and the reviewers re-ran on the new diff until clean. The audit that produced the final fix round caught, among other things: the `/api/tutors` list payload missing `concepts`/`level_labels` (frontend crashed on `tutor.concepts.find`), stale `activeConcept` state when switching tutors, registry validation gaps (zero concepts, blank persona, bad reference URLs), a mtime-only hot-reload cache, dead fields (`intro`), and unverified Khan Academy reference URLs.

## Validation loop

All Python validation ran in the conda env `/home/rohit/miniconda3/envs/llm/bin/python`:

1. `python -m pytest tests` for the FastAPI endpoints, tutor registry validation/hot-reload, agent metadata parsing, and the Redis state layer (using `fakeredis`).
2. `npx tsc --noEmit && npm run build` for the frontend.
3. `podman-compose up -d --build` and `curl` against the published API/frontend ports.
4. `podman-compose run --rm agent` with empty credentials to confirm a clean error message.

Where a check failed, I fixed the narrow issue and re-ran the same command before moving on.

## AI assistance style

- I used the models for **code skeleton, API introspection, and error diagnosis**, but I verified every external API call against the actual installed package.
- I kept the design document as the contract and did not let the implementation widen scope (no extra auth, no extra models, no mock voice demo).
- Human-in-the-loop happened only when a real decision was needed (none here; the approved plan was complete).

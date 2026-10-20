from __future__ import annotations

import asyncio
import logging
import sys

import livekit.agents as lka
import livekit.api as lkapi

from agent.session import finalize_session, run_session
from lib.config import AGENT_NAME, VALID_LLM_PROVIDERS, Settings, get_settings


def _preflight(settings: Settings) -> None:
    provider = settings.llm_provider.lower()
    if provider not in VALID_LLM_PROVIDERS:
        print(
            "ERROR: LLM_PROVIDER must be one of: "
            f"{', '.join(VALID_LLM_PROVIDERS)}. Got '{settings.llm_provider}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    missing: list[str] = []
    for name, value in (
        ("LIVEKIT_URL", settings.livekit_url),
        ("LIVEKIT_API_KEY", settings.livekit_api_key),
        ("LIVEKIT_API_SECRET", settings.livekit_api_secret),
        ("LLM_BASE_URL", settings.llm_base_url),
        ("LLM_API_KEY", settings.llm_api_key),
        ("LLM_MODEL", settings.llm_model),
        ("REDIS_URL", settings.redis_url),
    ):
        if not value:
            missing.append(name)

    if missing:
        print(
            "ERROR: Missing or invalid LiveKit/LLM credentials:\n  - "
            + "\n  - ".join(missing)
            + "\nPlease copy .env.example to .env and fill in the real values.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate LiveKit credentials with a quick, bounded API call so the worker
    # fails fast with a clear message instead of retrying and dumping a traceback.
    try:
        asyncio.run(_check_livekit(settings))
    except Exception as exc:
        print(
            "ERROR: Could not reach LiveKit Cloud with the provided credentials. "
            f"Check LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET. ({exc})",
            file=sys.stderr,
        )
        sys.exit(1)


async def _check_livekit(settings: Settings) -> None:
    async with lkapi.LiveKitAPI(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    ) as api:
        await asyncio.wait_for(
            api.room.list_rooms(lkapi.ListRoomsRequest()),
            timeout=10.0,
        )


# Module-level entrypoints are required so livekit-agents can pickle them for
# the per-job child processes. Settings are read from environment inside each
# process via get_settings().


async def entrypoint(ctx: lka.JobContext) -> None:
    await run_session(ctx, get_settings())


async def on_session_end(ctx: lka.JobContext) -> None:
    await finalize_session(ctx, get_settings())


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    _preflight(settings)

    server = lka.AgentServer(max_retry=3)
    # Register this worker under an explicit agent name. The API will request
    # an agent dispatch for the room after minting the token, so the worker
    # does not need to be running before the participant joins.
    # Verified against livekit-agents 1.8.8.
    server.rtc_session(
        entrypoint,
        agent_name=AGENT_NAME,
        on_session_end=on_session_end,
    )

    # livekit-agents 1.8.8's legacy CLI expects a subcommand (e.g. "start").
    # Make `python -m agent.worker` run the worker directly under compose.
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "start",
        "dev",
        "console",
        "connect",
        "download-files",
    }:
        sys.argv.append("start")

    try:
        lka.cli.run_app(server)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "livekit" in msg or "connect" in msg:
            print(
                "ERROR: Could not connect to LiveKit. "
                "Check LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in your .env file.",
                file=sys.stderr,
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Agent failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

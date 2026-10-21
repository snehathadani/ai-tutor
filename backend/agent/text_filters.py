"""Strip DeepSeek's DSML tool-call markup from model text.

DeepSeek models sometimes emit their internal tool syntax as *plain text*:

    <｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="get_problem"> ... </｜｜DSML｜｜ calls>

When that happens the markup is not a tool call, so it is spoken by TTS and
stored in the transcript. Tools still work through the normal path; this module
just guarantees the markup never reaches a listener or the transcript.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterable, AsyncGenerator

# The marker uses fullwidth vertical bars (U+FF5C), but accept ASCII pipes too.
_MARKER = re.compile(r"<[｜|]{2}\s*DSML", re.IGNORECASE)

# Enough characters to recognise a marker split across two stream chunks.
_HOLDBACK = 24


def strip_dsml_text(text: str) -> str:
    """Remove a leaked DSML block from text. Markup runs to the end of the turn."""
    match = _MARKER.search(text)
    if match is None:
        return text.strip()
    return text[: match.start()].strip()


async def strip_dsml_stream(stream: AsyncIterable[str]) -> AsyncGenerator[str, None]:
    """Text transform for ``tts_text_transforms``.

    Streams the text through with a small holdback so a marker split across
    chunks is still caught, then swallows everything from the marker onwards.
    """
    buffer = ""
    stopped = False
    async for chunk in stream:
        if stopped:
            continue
        buffer += chunk
        match = _MARKER.search(buffer)
        if match is not None:
            safe = buffer[: match.start()]
            stopped = True
            buffer = ""
            if safe:
                yield safe
            continue
        if len(buffer) > _HOLDBACK:
            yield buffer[:-_HOLDBACK]
            buffer = buffer[-_HOLDBACK:]
    if not stopped and buffer:
        yield buffer

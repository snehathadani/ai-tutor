"""Leaked DSML tool markup must never reach speech or the transcript."""

import pytest

from agent.text_filters import strip_dsml_stream, strip_dsml_text

LEAK = (
    "You're getting the hang of it! Let's try one more puzzle. "
    '<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="get_problem">'
    '<｜｜DSML｜｜ parameter name="concept_slug" string="true">sample-space'
    "</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ calls>"
)


def test_strip_text_keeps_the_spoken_part():
    assert strip_dsml_text(LEAK) == "You're getting the hang of it! Let's try one more puzzle."


def test_strip_text_leaves_normal_text_alone():
    clean = "How many outcomes does the coin have?"
    assert strip_dsml_text(clean) == clean


def test_markup_only_text_becomes_empty():
    assert strip_dsml_text('<｜｜DSML｜｜ calls> </｜｜DSML｜｜ calls>') == ""


def test_ascii_pipe_variant_is_also_stripped():
    assert strip_dsml_text('Nice! <||DSML|| calls> junk') == "Nice!"


@pytest.mark.asyncio
async def test_stream_transform_swallows_markup_split_across_chunks():
    async def source():
        yield "Good question. "
        yield '<｜｜DSML｜｜ cal'
        yield 'ls> <｜｜DSML｜｜ invoke name="get_problem">'
        yield " everything after the marker"

    chunks = [chunk async for chunk in strip_dsml_stream(source())]
    assert "".join(chunks) == "Good question. "


@pytest.mark.asyncio
async def test_stream_transform_passes_clean_text_through():
    async def source():
        yield "What is the chance "
        yield "of rolling a six?"

    chunks = [chunk async for chunk in strip_dsml_stream(source())]
    assert "".join(chunks) == "What is the chance of rolling a six?"

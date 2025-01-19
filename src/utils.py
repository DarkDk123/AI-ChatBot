"""
utils.py
---

It contains some utility functions.
"""

from langchain_chat import model
from typing import AsyncGenerator
import asyncio


def suggest_title(question: str):
    """Suggests title for a conversation."""

    return model.invoke(
        f"Suggest a max 3-4 word title for the given conversation start '{question}', \
                Asked to a spiritual Chat Bot on Rajneesh OSHO."
    ).content


def to_sync_generator(async_gen: AsyncGenerator):
    """
    Converts an AsyncGenerator to a SyncGenerator for streamlit to work.

    Refer: https://icandothese.com/docs/tech/machine_learning/streamlit_async_generator/
    """

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        while True:
            try:
                chunk = loop.run_until_complete(anext(async_gen))
                # print(chunk)
                yield chunk
            except StopAsyncIteration:
                break
    finally:
        loop.close()

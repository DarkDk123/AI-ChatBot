"""
utils.py
---

It contains some utility functions.
"""

import asyncio
import os

# from psycopg.rows import dict_row
from typing import AsyncGenerator, Optional

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg_pool import AsyncConnectionPool

# from src.agent.langgraph_chat import model, app as graph

PG_CONNECTION_POOL: Optional[AsyncConnectionPool] = None


# def suggest_title(question: str):
#     """Suggests title for a conversation."""

#     return model.invoke(
#         f"Suggest a max 3-4 word title for the given conversation start '{question}', \
#                 Asked to a spiritual Chat Bot on Rajneesh OSHO."
#     ).content


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
                chunk = loop.run_until_complete(anext(async_gen))  # noqa: F821
                # print(chunk)
                yield chunk
            except StopAsyncIteration:
                break
    finally:
        loop.close()


# Utils about Postgres
def _create_async_pool() -> AsyncConnectionPool:
    """Create an async connection pool with environment variables"""

    db_user = os.environ.get("POSTGRES_USER", "postgres")
    db_password = os.environ.get("POSTGRES_PASSWORD", "password")
    db_name = os.environ.get("POSTGRES_DB", "postgres")

    host_port = os.environ.get("DATABASE_URL", "postgres:5432").split(":")

    # Will this work with checkpointer??
    # connection_kwargs = {
    #     "prepare_threshold": 0,
    #     "row_factory": dict_row,
    # }

    return AsyncConnectionPool(
        conninfo=f"""
            dbname={db_name}
            user={db_user}
            password={db_password}
            host={host_port[0]}
            port={host_port[1]}
            sslmode=disable
        """,
        min_size=2,
        max_size=5,
        # connection_kwargs=connection_kwargs,
        open=False,
        # The default is going to change, so used False explicitly.
        # https://www.psycopg.org/psycopg3/docs/api/pool.html#the-connectionpool-class
    )


def get_async_pool() -> AsyncConnectionPool:
    """Get the async connection pool"""
    global PG_CONNECTION_POOL

    if not PG_CONNECTION_POOL:
        PG_CONNECTION_POOL = _create_async_pool()
    return PG_CONNECTION_POOL


async def get_checkpointer() -> tuple:
    # Initialize PostgreSQL checkpointer
    pool = get_async_pool()
    checkpointer = AsyncPostgresSaver(pool)  # type:ignore
    await checkpointer.setup()
    return checkpointer, pool


async def response_generator(
    thread_id: str, message: str, *, graph: CompiledStateGraph
):
    config = RunnableConfig(
        configurable={"thread_id": thread_id},
    )

    async for message, metadata in graph.astream(
        {"messages": [("user", message)]},
        config,
        stream_mode="messages",
    ):
        if (
            isinstance(message, AIMessageChunk)
            and isinstance(metadata, dict)
            and metadata["langgraph_node"] == "model"
        ):
            # if message.response_metadata.get("finish_reason", None) == "stop":
            #     # Streaming done!
            #     print(message.content, " >>> END")
            #     break
            yield str(message.content + "\n\n")  # type:ignore

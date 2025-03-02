"""
utils.py
---

It contains some utility functions.
"""

import asyncio
import logging
import os
from functools import lru_cache
from typing import AsyncGenerator, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

PG_CONNECTION_POOL: Optional[AsyncConnectionPool] = None


def suggest_title(question: str) -> str:
    """Suggests title for a conversation."""

    return str(
        get_llm(temperature=0.5, max_tokens=10)
        .invoke(
            f"Suggest a max concise title for the given conversation start '{question}', \
                Asked to a Impersonate Chat Bot on Rajneesh OSHO, the philosopher."
        )
        .content
    )


# Fetch LLM settings from environment variables
LLM_MODEL_ENGINE = os.environ.get("LLM_MODEL_ENGINE", "groq")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "llama-3.1-8b-instant")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", None)


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

    connection_kwargs = {
        "prepare_threshold": 0,
        # "row_factory": dict_row,
        "autocommit": True,
    }

    logger.info("Creating async connection pool with the following settings:")
    logger.info(f"Database User: {db_user}")
    logger.info(f"Database Name: {db_name}")
    logger.info(f"Host: {host_port[0]}")
    logger.info(f"Port: {host_port[1]}")

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
        kwargs=connection_kwargs,
        open=False,
        # The default is going to change, so used False explicitly.
        # https://www.psycopg.org/psycopg3/docs/api/pool.html#the-connectionpool-class
    )


def get_async_pool() -> AsyncConnectionPool:
    """Get the async connection pool"""
    global PG_CONNECTION_POOL

    if not PG_CONNECTION_POOL:
        logger.info("Async connection pool not found, creating a new one.")
        PG_CONNECTION_POOL = _create_async_pool()
    else:
        logger.info("Using existing async connection pool.")
    return PG_CONNECTION_POOL


async def get_checkpointer(
    open=False,
) -> tuple[AsyncPostgresSaver, AsyncConnectionPool]:
    # Initialize PostgreSQL checkpointer
    logger.info("Initializing PostgreSQL checkpointer")
    pool = get_async_pool()

    if open:
        await pool.open()

    checkpointer = AsyncPostgresSaver(pool)  # type:ignore

    logger.info("Setting up PostgreSQL checkpointer")
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


@lru_cache()
def get_llm(**kwargs) -> BaseChatModel:
    """Create the LLM connection."""

    if LLM_MODEL_ENGINE == "groq":
        # Get the unused parameters
        unused_params = [
            key
            for key in kwargs.keys()
            if key not in ["temperature", "top_p", "max_tokens"]
        ]

        if unused_params:
            logger.warning(
                f"The following parameters from kwargs are not supported: {unused_params} for {LLM_MODEL_ENGINE}"
            )

        if LLM_BASE_URL:
            logger.info(f"Using llm model {LLM_MODEL_NAME} hosted at {LLM_BASE_URL}")
            return ChatGroq(
                base_url=LLM_BASE_URL,
                model=LLM_MODEL_NAME,
                api_key=LLM_API_KEY,  # type:ignore
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", None),
                model_kwargs={"top_p": kwargs.get("top_p", 0.90)},
            )
        else:
            logger.info(f"Using llm model {LLM_MODEL_NAME} from api catalog")
            return ChatGroq(
                model=LLM_MODEL_NAME,
                api_key=LLM_API_KEY,  # type:ignore
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", None),
                model_kwargs={"top_p": kwargs.get("top_p", 0.90)},
            )
    else:
        raise RuntimeError(
            "Unable to find any supported Large Language Model server. Supported engine name is groq."
        )


async def remove_state_from_checkpointer(thread_id):
    async with get_async_pool().connection() as connection:
        async with connection.cursor() as cursor:
            try:
                # Execute delete commands
                await cursor.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,)
                )
                await cursor.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,)
                )
                await cursor.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,)
                )

                logger.info(f"Deleted Checkpointer rows with thread_id: {thread_id}")

            except Exception as e:
                logger.info(
                    f"Error occurred while deleting data from checkpointer: {e}"
                )

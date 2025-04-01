"""API Server for ChatBot Endpoints."""

import asyncio
import logging
import os
import random
import re
import time
from contextlib import asynccontextmanager
from traceback import print_exc
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import (
    AIMessageChunk,
    HumanMessage,
)
from langchain_core.runnables import RunnableConfig
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from src.chatbot.auth import SECRET_KEY, create_users_table, get_current_user, router
from src.chatbot.cache.cache_manager import CacheManager
from src.chatbot.datastore.datastore import Datastore
from src.chatbot.main import CompiledStateGraph, get_agent
from src.chatbot.schemas import (
    FALLBACK_RESPONSES,
    ChainResponse,
    ChainResponseChoices,
    CreateThreadResponse,
    DeleteThreadResponse,
    GetThreadResponse,
    Message,
    Prompt,
    fallback_response_generator,
)
from src.chatbot.utils import get_async_pool, remove_state_from_checkpointer

logging.basicConfig(level=os.getenv("LOG_LEVEL", logging.INFO))
logger = logging.getLogger(__name__)
logger.info("Initializing Chatbot API app...")

# Initialize app
cache: CacheManager
datastore: Datastore
agent: CompiledStateGraph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan of the FastAPI app."""
    # Load required resources
    global cache, datastore, agent

    async_pool = get_async_pool()
    await async_pool.open(wait=True)
    print("✌️ Connections got!!!")

    cache = CacheManager()
    datastore = Datastore()
    agent = await get_agent()

    await datastore.database.init_script()
    await create_users_table(async_pool)

    yield

    # Clean up the resources
    await async_pool.close()


# FastAPI app
app = FastAPI(title="Osho Chatbot API", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.include_router(router)


# Routes
@app.get("/healthz")
def healthz():
    """Health Check for Chatbot Server."""
    return {"status": "ok", "message": "ChatBot API service is healthy"}


@app.get(
    "/create_thread",
    tags=["Thread Management"],
    response_model=CreateThreadResponse,
    responses={
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error occurred"}
                }
            },
        }
    },
)
async def create_thread(
    user_id: str, current_user: dict = Depends(get_current_user)
) -> CreateThreadResponse:
    """Create a new conversation thread."""

    # Try for fix number of time, if no unique thread_id is found raise Error
    for _ in range(5):
        thread_id = str(uuid4())

        # Ensure thread_id created does not exist in cache
        if not cache.is_valid_thread(thread_id):
            # Ensure thread_id created does not exist in datastore (permanenet store like postgres)
            if not await datastore.is_valid_thread(thread_id):
                # Create a thread on cache for validation
                if cache.create_conversation_thread(thread_id, user_id):
                    if await datastore.save_update_thread(
                        thread_id=thread_id,
                        **cache.get_thread_info(thread_id),
                    ):
                        return CreateThreadResponse(thread_id=thread_id)
                    raise HTTPException(
                        status_code=500, detail="Unable to save thread_id"
                    )

    raise HTTPException(status_code=500, detail="Unable to generate thread_id")


@app.post(
    "/generate",
    tags=["Inference"],
    response_model=ChainResponse,
    responses={
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error occurred"}
                }
            },
        }
    },
)
async def generate_answer(
    request: Request, prompt: Prompt, current_user: dict = Depends(get_current_user)
) -> StreamingResponse:
    """Generate and stream the response to the provided prompt."""

    logger.info(f"Input at /generate endpoint of Agent: {prompt.model_dump()}")

    try:
        user_query_timestamp = time.time()

        # Handle invalid thread id
        if not cache.is_valid_thread(prompt.thread_id):
            if not await datastore.is_valid_thread(prompt.thread_id):
                logger.info("No conversation found in cache or database")
                logger.error(
                    f"No thread_id found in database for {prompt.thread_id}. Please create thread id before generate request."
                )
                print_exc()
                return StreamingResponse(
                    fallback_response_generator(
                        sentence=random.choice(FALLBACK_RESPONSES),
                        thread_id=prompt.thread_id,
                    ),
                    media_type="text/event-stream",
                )

            thread_info = await datastore.get_thread_info(prompt.thread_id)
            if thread_info:
                cache.update_conversation_thread(**thread_info)

            else:
                logger.info("No conversation found in cache or database")
                raise HTTPException(404, detail="Invalid Thread info found!")

        chat_history = prompt.messages
        # The last user message will be the query for the rag or llm chain
        last_user_message = next(
            (
                message.content
                for message in reversed(chat_history)
                if message.role == "user"
            ),
            None,
        )

        # Normalize the last user input and remove non-ascii characters
        last_user_message = re.sub(
            r"[^\x00-\x7F]+", "", last_user_message or ""
        )  # Remove all non-ascii characters

        last_user_message = re.sub(
            r"[\u2122\u00AE]", "", last_user_message
        )  # Remove standard trademark and copyright symbols

        last_user_message = last_user_message.replace("~", "-")

        logger.info(f"Normalized user input: {last_user_message}")

        # Keep copy of unmodified query to store in db
        user_query = last_user_message

        async def response_generator():
            resp_id = str(uuid4())
            resp_str = ""

            chain_response = ChainResponse(thread_id=prompt.thread_id)
            config = RunnableConfig(
                configurable={"thread_id": prompt.thread_id},
            )

            input_messages = [HumanMessage(last_user_message)]
            async for message, metadata in agent.astream(
                {"messages": input_messages},
                config,
                stream_mode="messages",
            ):
                if (
                    isinstance(message, AIMessageChunk)
                    and isinstance(metadata, dict)
                    and metadata["langgraph_node"] == "model"
                ):
                    resp_str += str(message.content)

                    if message.response_metadata.get("finish_reason", None) == "stop":
                        # Streaming done!
                        print(message.content, " >>> END")
                        break
                    print(message.content, end=" | ")
                    # print(input_messages)

                    response_choice = ChainResponseChoices(
                        index=0,
                        message=Message(role="assistant", content=str(message.content)),
                    )

                    chain_response.id = resp_id
                    chain_response.choices.append(response_choice)
                    logger.debug(response_choice)

                    yield str(chain_response.model_dump()) + "\n\n"

                chain_response = ChainResponse(thread_id=prompt.thread_id)

            # Initialize content with space to overwrite default response
            response_choice = ChainResponseChoices(
                index=0,
                message=Message(role="assistant", content=" "),
                finish_reason="[DONE]",
            )

            logger.info(
                f"Conversation saved:\nThread ID: {prompt.thread_id}\nQuery: {last_user_message}\nResponse: {resp_str}"
            )
            logger.info("Saving to both cache and pg database")

            # Saving to cache & Database
            response_timestamp = time.time()

            # Cache should fetch thread from db first. (Fetched above)
            cache.update_conversation_thread(
                prompt.thread_id,
                prompt.user_id or "default",
                [
                    Message(
                        role="user",
                        content=user_query,
                        timestamp=f"{user_query_timestamp}",
                    ).model_dump(),
                    Message(
                        role="assistant",
                        content=resp_str,
                        timestamp=f"{response_timestamp}",
                    ).model_dump(),
                ],
                last_conversation_time=user_query_timestamp,
            )

            # Can go to FastAPI's Background process. [for low latency]
            await datastore.save_update_thread(
                prompt.thread_id,
                prompt.user_id or "default",
                [
                    Message(
                        role="user",
                        content=user_query,
                        timestamp=f"{user_query_timestamp}",
                    ).model_dump(),
                    Message(
                        role="assistant",
                        content=resp_str,
                        timestamp=f"{response_timestamp}",
                    ).model_dump(),
                ],
                last_conversation_time=user_query_timestamp,
            )

            chain_response.id = resp_id
            chain_response.choices.append(response_choice)
            logger.debug(response_choice)

            yield str(chain_response.model_dump()) + "\n\n"

        return StreamingResponse(response_generator(), media_type="text/event-stream")
    # Catch any unhandled exceptions
    except asyncio.CancelledError:
        # Handle the cancellation gracefully
        logger.error(
            "Unhandled Server interruption before response completion. Details: {e}"
        )
        print_exc()
        return StreamingResponse(
            fallback_response_generator(
                sentence=random.choice(FALLBACK_RESPONSES), thread_id=prompt.thread_id
            ),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.error(f"Unhandled Error from /generate endpoint. Error details: {e}")
        print_exc()
        return StreamingResponse(
            fallback_response_generator(
                sentence=random.choice(FALLBACK_RESPONSES), thread_id=prompt.thread_id
            ),
            media_type="text/event-stream",
        )


# Get conversation
@app.get(
    "/get_thread_info",
    tags=["Thread Management"],
    response_model=GetThreadResponse,
    responses={
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error occurred"}
                }
            },
        }
    },
)
async def get_thread_info(thread_id, current_user: dict = Depends(get_current_user)):
    """Get conversation_thread info from cache or database."""
    logger.info(f"Getting conversation for {thread_id}")
    if not cache.is_valid_thread(thread_id):
        if not await datastore.is_valid_thread(thread_id):
            logger.info("No conversation found in thread or database")
            raise HTTPException(404, detail="Thread info not found")

        thread_info = await datastore.get_thread_info(thread_id)
        if thread_info:
            cache.update_conversation_thread(**thread_info)

        else:
            logger.info("No conversation found in thread or database")
            raise HTTPException(404, detail="Invalid thread info found!")

    thread_info = cache.get_thread_info(thread_id)
    logger.info(f"Get Thread info: {thread_info}")

    return GetThreadResponse(
        thread_id=thread_id,
        user_id=thread_info["user_id"],
        conversation_history=thread_info["conversation_history"],
    )


@app.delete(
    "/delete_thread",
    tags=["Thread Management"],
    response_model=DeleteThreadResponse(),
    responses={
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error occurred"}
                }
            },
        }
    },
)
async def delete_thread(thread_id, current_user: dict = Depends(get_current_user)):
    """Delete conversation_thread from cache and database."""

    logger.info(f"Deleting conversation for {thread_id}")

    thread_info = cache.is_valid_thread(thread_id)
    datastore_thread_info = await datastore.is_valid_thread(thread_id)

    if not (thread_info or datastore_thread_info):
        logger.info("No conversation found in db")
        return DeleteThreadResponse(message="Thread info not found")

    logger.info(f"Deleting conversation for {thread_id} from cache")
    cache.delete_conversation_thread(thread_id)

    logger.info(f"Deleting conversation for {thread_id} in database")
    await datastore.delete_conversation_thread(thread_id)

    logger.info(f"Deleting checkpointer for {thread_id}")
    await remove_state_from_checkpointer(thread_id)

    return DeleteThreadResponse(message="Thread info deleted")


# Request Validation Exception handling
@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Request Validation Exception Handler"""

    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors(), exclude={"input"})},
    )


logger.info("ChatBot-API service initialized...")

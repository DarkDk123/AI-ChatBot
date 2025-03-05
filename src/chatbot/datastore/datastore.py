"""
Datastore to store user conversations in database.

Uses one of :
    - PostgresClient
"""

import os
import time
from datetime import datetime
from typing import Optional

from src.chatbot.datastore.postgres_client import PostgresClient

# from src.agent.datastore.redis_client import RedisClient


class Datastore:
    def __init__(self):
        """Initialize Datastore"""

        db_name = os.environ.get("DATABASE_NAME", "postgres")
        if db_name == "postgres":
            print("Using postgres to store conversation history")
            self.database = PostgresClient()
        # elif db_name == "redis":
        #     print("Using Redis to store conversation history")
        #     self.database = RedisClient()
        else:
            raise ValueError(
                f"{db_name} database in not supported. Supported type postgres"
            )

    async def save_update_thread(
        self,
        thread_id: str,
        user_id: str,
        conversation_history: list,
        start_conversation_time: Optional[float | str] = None,
        last_conversation_time: Optional[float | str] = None,
    ):
        """Save or Update a conversation for the given details"""

        # Validate from str if required
        if isinstance(start_conversation_time, str):
            try:
                datetime.fromisoformat(start_conversation_time)
            except ValueError:
                raise ValueError(
                    "Start conversation time must be in valid ISO format string."
                )
        else:
            start_conversation_time = datetime.fromtimestamp(
                start_conversation_time or time.time()
            ).strftime("%Y-%m-%d %H:%M:%S.%f")

        if isinstance(last_conversation_time, str):
            try:
                datetime.fromisoformat(last_conversation_time)
            except ValueError:
                raise ValueError(
                    "Last conversation time must be in valid ISO format string."
                )
        else:
            last_conversation_time = datetime.fromtimestamp(
                last_conversation_time or time.time()
            ).strftime("%Y-%m-%d %H:%M:%S.%f")

        return await self.database.save_update_thread(
            thread_id,
            user_id,
            conversation_history,
            start_conversation_time,
            last_conversation_time,
        )

    async def is_valid_thread(self, thread_id: str) -> bool:
        """Check if thread_id already exist in database."""
        return await self.database.is_thread(thread_id)

    async def get_thread_info(self, thread_id: str):
        """Fetch conversation for given thread id"""
        return await self.database.get_thread_info(thread_id)

    async def delete_conversation_thread(self, thread_id: str):
        """Delete conversation for given thread id"""
        await self.database.delete_conversation_thread(thread_id)

    async def get_thread_messages(self, thread_id: str):
        """Retrieve the entire conversation history from database as a list."""
        return await self.database.get_thread_messages(thread_id)

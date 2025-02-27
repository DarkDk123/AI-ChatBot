"""
Datastore to store user conversations in database.

Uses one of :
    - PostgresClient
"""

import os
import time
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
        user_id: Optional[str],
        conversation_history: list,
        start_conversation_time: Optional[float] = None,
        last_conversation_time: Optional[float] = None,
    ):
        """Save or Update a conversation for the given details"""

        await self.database.save_update_thread(
            thread_id,
            user_id,
            conversation_history,
            start_conversation_time,
            last_conversation_time or time.time(),
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

    async def update_thread_messages(self, thread_id: str, messages: list):
        """Update conversation in database. Error if not exists"""
        await self.database.update_thread_messages(thread_id, messages)

"""
Cache Manager utilizing an underlying cache manager.

Cache Manager manages message timings, conversation history
based on a thread_id.
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional

from src.chatbot.cache.local_cache import LocalCache
from src.chatbot.cache.redis_client import RedisClient


class CacheManager:
    """
    Cache Manager utilizing an underlying cache manager.

    Store the conversation between user and assistant, it's stored in format

    ```
    {
        "thread_id": {
            "user_id": "",
            "conversation_history": [
                {
                    "role": "user/assistant",
                    "content": "",
                    "timestamp": "2004-10-19 10:23:54"
                }
            ],
            "start_conversation_time": "2004-10-19 10:23:54",
            "last_conversation_time": "2004-10-19 10:23:54"
        }
    }
    ```
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize cache manager, based on the config automatically.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """

        db_name = os.environ.get("CACHE_NAME", "inmemory")
        if db_name == "redis":
            print("Using Redis client for user history")
            self.memory = RedisClient()
        elif db_name == "inmemory":
            print("Using python dict for user history")
            self.memory = LocalCache()
        else:
            raise ValueError(
                f"{db_name} in not supported. Supported type redis, inmemory"
            )

    def update_conversation_thread(
        self,
        thread_id: str,
        user_id: str,
        conversation_history: List,
        start_conversation_time: Optional[float | str] = None,
        last_conversation_time: Optional[float | str] = None,
    ) -> bool:
        """Save conversation to the given thread_id."""

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

        return self.memory.update_conversation_thread(
            thread_id,
            user_id,
            conversation_history,
            start_conversation_time,
            last_conversation_time,
        )

    def is_valid_thread(self, thread_id: str) -> bool:
        """Check if thread_id already exist in cache."""
        return self.memory.is_thread(thread_id)

    def get_thread_info(self, thread_id: str) -> Dict:
        """Retrieve complete thread information from cache."""
        return self.memory.get_thread_info(thread_id)

    def response_feedback(self, thread_id: str, response_feedback: float) -> bool:
        """Save given thread feedback in cache."""
        return self.memory.response_feedback(thread_id, response_feedback)

    def delete_conversation_thread(self, thread_id: str):
        """Delete conversation for given thread id."""
        return self.memory.delete_conversation_thread(thread_id)

    def create_conversation_thread(self, thread_id: str, user_id: str = ""):
        """Create a entry for given thread id."""
        return self.memory.create_conversation_thread(thread_id, user_id)

    def get_thread_messages(self, thread_id: str):
        """Retrieve the entire conversation history from cache as a list."""
        return self.memory.get_messages(thread_id)

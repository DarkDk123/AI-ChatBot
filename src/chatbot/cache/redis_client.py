"""
Redis Cache Manager.

Redis Cache Manager for working with conversation history
based on thread_id using redis.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import redis


class RedisClient:
    def __init__(self) -> None:
        """Create a Redis client to manage conversation history."""

        # convert hours into second as redis takes expiry time in seconds
        self.expiry = int(os.getenv("REDIS_SESSION_EXPIRY", 12)) * 60 * 60
        print(f"Redis Cache expiry {self.expiry} seconds")

        host, port = os.getenv("CACHE_URL", "redis:6379").split(":")
        db = int(os.getenv("REDIS_DB", "0"))
        print(f"Host: {host}, Port: {port}, DB: {db}")

        self.redis_client = redis.Redis(
            host=host,
            port=int(port),
            db=db,
            decode_responses=True,
        )

    def get_messages(self, thread_id: str) -> List:
        """Retrieve the entire conversation history from Redis as a list."""

        conversation_history = self.redis_client.lrange(
            f"{thread_id}:conversation_history", 0, -1
        )

        return [json.loads(conv) for conv in conversation_history]

    def get_k_messages(self, thread_id: str, k_turn: Optional[int] = None) -> List:
        """Retrieve the last k conversations from Redis."""

        # TODO: Evaluate this implementation
        if k_turn is None:
            k_turn = -1
        conversation_history = self.redis_client.lrange(
            f"{thread_id}:conversation_history", -k_turn, -1
        )

        return [json.loads(conv) for conv in conversation_history]

    def update_conversation_thread(
        self,
        thread_id: str,
        user_id: str,
        conversation_history: List,
        start_conversation_time: Optional[float],
        last_conversation_time: Optional[float],
    ) -> bool:
        """Update conversation to Redis cache. Error if not exists"""
        if not self.is_thread(thread_id):
            self.create_conversation_thread(thread_id, user_id)

        try:
            # Store start conversation time only if it doesn't exist
            start_time_key = f"{thread_id}:start_conversation_time"
            last_time_key = f"{thread_id}:last_conversation_time"

            existing_start = self.redis_client.get(start_time_key)
            self.redis_client.set(
                start_time_key,
                (
                    datetime.fromtimestamp(start_conversation_time)
                    if start_conversation_time is not None
                    else (
                        datetime.fromisoformat(existing_start)
                        if existing_start
                        else datetime.now()
                    )
                ).strftime("%Y-%m-%d %H:%M:%S.%f"),
                ex=self.expiry,
            )

            # Last Conversation time
            self.redis_client.set(
                last_time_key,
                (
                    datetime.fromtimestamp(last_conversation_time or time.time())
                ).strftime("%Y-%m-%d %H:%M:%S.%f"),
                ex=self.expiry,
            )
            self.redis_client.set(f"{thread_id}:user_id", user_id, ex=self.expiry)

            # Add conversation history
            self.redis_client.rpush(
                f"{thread_id}:conversation_history",
                *[json.dumps(conv) for conv in conversation_history],
            )

            return True
        except redis.RedisError as e:
            print(
                f"RedisError: Unable to update conversation for thread {thread_id}. Error: {str(e)}"
            )
            return False

    def is_thread(self, thread_id: str) -> bool:
        """Check if thread_id already exist in cache."""

        return self.redis_client.exists(f"{thread_id}:start_conversation_time")

    def get_thread_info(self, thread_id: str) -> Dict:
        """Retrieve complete thread information from cache."""

        resp = {}
        conversation_history = self.redis_client.lrange(
            f"{thread_id}:conversation_history", 0, -1
        )
        resp["conversation_history"] = [
            json.loads(conv) for conv in conversation_history
        ]
        resp["user_id"] = self.redis_client.get(f"{thread_id}:user_id")
        resp["last_conversation_time"] = self.redis_client.get(
            f"{thread_id}:last_conversation_time"
        )
        resp["start_conversation_time"] = self.redis_client.get(
            f"{thread_id}:start_conversation_time"
        )

        return resp

    def response_feedback(self, thread_id: str, response_feedback: float) -> bool:
        """Save last thread feedback in Redis cache."""

        try:
            # Get the key for the conversation history
            conv_key = f"{thread_id}:conversation_history"

            # Check if the conversation history exists
            if not self.redis_client.exists(conv_key):
                print(f"No conversation history found for thread {thread_id}")
                return False

            # Get the last conversation entry
            last_conv = self.redis_client.lindex(conv_key, -1)
            if not last_conv:
                print(f"Conversation history is empty for thread {thread_id}")
                return False

            # Parse the last conversation, add feedback, and update in Redis
            conv_data = json.loads(last_conv)
            conv_data["feedback"] = response_feedback
            updated_conv = json.dumps(conv_data)

            # Replace the last entry with the updated one
            self.redis_client.lset(conv_key, -1, updated_conv)

            return True

        except json.JSONDecodeError:
            print(
                f"JSONDecodeError: Unable to parse conversation data for thread {thread_id}"
            )
            return False
        except ValueError as e:
            print(f"ValueError: {str(e)}")
            return False
        except redis.RedisError as e:
            print(f"RedisError: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error while storing user feedback: {str(e)}")
            return False

    def delete_conversation_thread(self, thread_id: str) -> bool:
        """Delete conversation for the given thread id."""

        try:
            # Define the keys to delete
            keys_to_delete = [
                f"{thread_id}:conversation_history",
                f"{thread_id}:user_id",
                f"{thread_id}:last_conversation_time",
                f"{thread_id}:start_conversation_time",
            ]

            # Use pipeline to delete keys, checking if they exist
            pipeline = self.redis_client.pipeline()
            for key in keys_to_delete:
                # Only delete if the key exists
                if self.redis_client.exists(key):
                    pipeline.delete(key)

            pipeline.execute()

            print(
                f"Deleted conversation history and associated data for thread ID: {thread_id}"
            )
            return True

        except redis.RedisError as e:
            print(
                f"RedisError: Unable to delete conversation for thread {thread_id}. Error: {str(e)}"
            )
            return False
        except Exception as e:
            print(f"Unexpected error while deleting conversation: {str(e)}")
            return False

    def create_conversation_thread(self, thread_id: str, user_id: str = ""):
        """Create an entry for a given thread id."""

        try:
            # Store start conversation time only if it doesn't exist
            start_time_key = f"{thread_id}:start_conversation_time"

            if self.is_thread(thread_id):
                print(f"Thread {thread_id} already exists in cache.")
                return False

            pipeline = self.redis_client.pipeline()
            pipeline.set(
                start_time_key,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                ex=self.expiry,
            )
            pipeline.set(
                f"{thread_id}:last_conversation_time",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                ex=self.expiry,
            )

            pipeline.rpush(f"{thread_id}:conversation_history", *[])
            pipeline.expire(f"{thread_id}:conversation_history", self.expiry)

            pipeline.set(f"{thread_id}:user_id", user_id, ex=self.expiry)

            pipeline.execute()
            return True
        except Exception as e:
            print(f"Failed to create thread due to exception {e}")
            return False

    def update_thread_messages(self, thread_id: str, messages: List):
        """Update conversation in cache. Error if not exists"""

        if not self.is_thread(thread_id):
            print(f"Thread {thread_id} not found in cache.")
            return False

        self.redis_client.rpush(f"{thread_id}:conversation_history", *messages)
        return True

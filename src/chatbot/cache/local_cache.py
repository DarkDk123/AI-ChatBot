"""
Local in-memory Cache.

Cache Manager for working with conversation history
based on thread_id using python dict
"""

from datetime import datetime
from typing import Dict, List


class LocalCache:
    # Maintain conversation history thread_id: Dict
    cache_data = {}

    def get_messages(self, thread_id: str) -> Dict:
        """Retrieve the entire conversation history from `in-memory` cache as a list."""

        return self.cache_data.get(thread_id, {}).get("conversation_history", [])

    def update_conversation_thread(
        self,
        thread_id: str,
        user_id: str,
        conversation_history: List,
        start_conversation_time: str,
        last_conversation_time: str,
    ) -> bool:
        """Update conversation in `in-memory` cache. Error if not exists"""
        try:
            if not self.is_thread(thread_id):
                self.create_conversation_thread(thread_id, user_id)

            existing_start = self.cache_data.get(thread_id, {}).get(
                "start_conversation_time", start_conversation_time
            )

            self.cache_data[thread_id].update(
                {
                    "user_id": (
                        user_id
                        if user_id is not None
                        else self.cache_data.get(thread_id, {}).get("user_id", "")
                    ),
                    "conversation_history": self.cache_data.get(thread_id, {}).get(
                        "conversation_history", []
                    )
                    + conversation_history,
                    "start_conversation_time": existing_start
                    or start_conversation_time,
                    "last_conversation_time": last_conversation_time,
                }
            )
            return True
        except Exception as e:
            print(f"Failed to update conversation due to exception {e}")
            return False

    def is_thread(self, thread_id: str) -> bool:
        """Check if thread_id already exist in cache."""

        return thread_id in self.cache_data

    def get_thread_info(self, thread_id: str) -> Dict:
        """Retrieve complete thread information from cache."""

        return self.cache_data.get(thread_id, {})

    def response_feedback(self, thread_id: str, response_feedback: float) -> bool:
        """Save given thread feedback in `in-memory` cache."""
        try:
            thread = self.cache_data.get(thread_id)
            if not thread:
                return False

            conversation_history = thread.get("conversation_history")
            if not conversation_history:
                print(f"No conversation history found for thread {thread_id}")
                return False

            conversation_history[-1]["feedback"] = response_feedback
            return True
        except KeyError as e:
            print(f"KeyError: Unable to store user feedback. Missing key: {e}")
            return False
        except IndexError:
            print(f"IndexError: Conversation history is empty for thread {thread_id}")
            return False
        except Exception as e:
            print(f"Unexpected error while storing user feedback: {e}")
            return False

    def delete_conversation_thread(self, thread_id: str) -> bool:
        """Delete conversation for given thread id."""

        if self.is_thread(thread_id):
            del self.cache_data[thread_id]
            print(f"Deleted conversation history for thread ID: {thread_id}")
            return True
        print(f"No conversation history found for thread ID {thread_id}")
        return False

    def create_conversation_thread(self, thread_id: str, user_id: str = ""):
        """Create an entry for a given thread id."""

        try:
            if self.is_thread(thread_id):
                print(f"Thread {thread_id} already exists in cache.")
                return False

            self.cache_data[thread_id] = {
                "user_id": user_id or "",
                "conversation_history": [],
                "last_conversation_time": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                ),
                "start_conversation_time": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                ),
            }
            return True
        except Exception as e:
            print(f"Failed to create thread due to exception {e}")
            return False

    def update_thread_messages(self, thread_id: str, messages: List):
        """Update conversation in cache. Error if not exists"""

        if not self.is_thread(thread_id):
            print(f"Thread {thread_id} not found in cache.")
            return False

"""
PostgreSQL Datastore Client using psycopg with connection pooling.

Manages conversation history with connection pooling and automatic table creation.
This client utilizes `raw SQL` to perform it's operations.
"""

# import asyncio
from typing import Dict, List, Optional

from psycopg import sql
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from src.chatbot.utils import get_async_pool


class PostgresClient:
    """
    PostgresClient to manage persistent conversation data.

    ```
    {
        "thread_id": "str",
        "user_id": "str",
        "conversation_history": [
            {
                "role": "user/assistant",
                "content": "",
                "timestamp": ""
            }
        ],
        "last_conversation_time": "",
        "start_conversation_time": ""
    }
    ```
    """

    def __init__(self):
        """Initialize PostgresClient"""

        self.pool: AsyncConnectionPool = get_async_pool()

        # Call init_script asynchronously
        # asyncio.run(self.init_script())

    # def __create_async_pool(self) -> AsyncConnectionPool:
    #     """Create a connection pool with environment variables"""

    #     db_user = os.environ.get("POSTGRES_USER", "postgres")
    #     db_password = os.environ.get("POSTGRES_PASSWORD", "password")
    #     db_name = os.environ.get("POSTGRES_DB", "postgres")

    #     settings = get_config()
    #     host_port = settings.database.url.split(":")

    #     return AsyncConnectionPool(
    #         conninfo=f"""
    #             dbname={db_name}
    #             user={db_user}
    #             password={db_password}
    #             host={host_port[0]}
    #             port={host_port[1]}
    #             sslmode=disable
    #         """,
    #         min_size=1,
    #         max_size=5,
    #     )

    async def init_script(self):
        """Initialize database table if not exists"""
        create_table_sql = sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                thread_id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                last_conversation_time TIMESTAMP,
                start_conversation_time TIMESTAMP,
                conversation_data JSONB
            );
        """
        )

        async with self.pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(create_table_sql)
                await conn.commit()

    async def save_update_thread(
        self,
        thread_id: str,
        user_id: str,
        conversation_history: List[Dict],
        start_conversation_time: str,
        last_conversation_time: str,
    ):
        """
        Upsert conversation data using ON CONFLICT update.

        Needs conversation timings as datetime.
        """
        # TODO: Potential buggy Query.

        insert_sql = sql.SQL(
            """
            INSERT INTO conversation_history (
                thread_id,
                user_id,
                start_conversation_time,
                last_conversation_time,
                conversation_data
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (thread_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                last_conversation_time = EXCLUDED.last_conversation_time,
                conversation_data = conversation_history.conversation_data || EXCLUDED.conversation_data
        """
        )

        # Execute
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        insert_sql,
                        (
                            thread_id,
                            user_id if user_id else None,
                            start_conversation_time,
                            last_conversation_time,
                            Json(conversation_history),
                        ),
                    )
                    await conn.commit()
        except Exception as e:
            print(f"Error storing conversation: {e}")
            # TODO: Maybe this isn't required.
            # There may be multiples like this
            # await conn.rollback()

    async def get_thread_info(self, thread_id: str) -> Optional[Dict]:
        """Retrieve conversation data by thread_id"""
        select_sql = sql.SQL(
            """
            SELECT
                thread_id,
                user_id,
                last_conversation_time,
                start_conversation_time,
                conversation_data
            FROM conversation_history
            WHERE thread_id = %s
        """
        )

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(select_sql, (thread_id,))
                    result = await cursor.fetchone()

                    if result:
                        return {
                            "thread_id": result[0],
                            "user_id": result[1],
                            "last_conversation_time": result[2],
                            "start_conversation_time": result[3],
                            "conversation_history": result[4],
                        }
                    return None
        except Exception as e:
            print(f"Error fetching conversation: {e}")
            return None

    async def delete_conversation_thread(self, thread_id: str):
        """Delete conversation by thread_id"""
        delete_sql = sql.SQL(
            """
            DELETE FROM conversation_history
            WHERE thread_id = %s
        """
        )

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(delete_sql, (thread_id,))
                    await conn.commit()
                    print(f"Deleted conversation {thread_id}")
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            # await conn.rollback()

    async def is_thread(self, thread_id: str) -> bool:
        """Check if session exists"""
        exists_sql = sql.SQL(
            """
            SELECT EXISTS(
                SELECT 1
                FROM conversation_history
                WHERE thread_id = %s
            )
        """
        )

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(exists_sql, (thread_id,))
                    result = await cursor.fetchone()
                    return result[0] if result else False
        except Exception as e:
            print(f"Error checking session existence: {e}")
            return False

    async def get_thread_messages(self, thread_id: str) -> Optional[List[Dict]]:
        """Retrieve the entire conversation history by thread_id"""

        select_sql = sql.SQL(
            """
            SELECT conversation_data
            FROM conversation_history
            WHERE thread_id = %s
        """
        )

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(select_sql, (thread_id,))
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"Error fetching messages: {e}")
            return None

    async def update_thread_messages(self, thread_id: str, messages: List[Dict]):
        """Update conversation messages by thread_id"""
        update_sql = sql.SQL(
            """
            UPDATE conversation_history
            SET conversation_data = conversation_data || %s::jsonb
            WHERE thread_id = %s
        """
        )

        if not self.is_thread(thread_id):
            raise KeyError(f"Thread {thread_id} not found in database.")

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(update_sql, (Json(messages), thread_id))
                    await conn.commit()
        except Exception as e:
            print(f"Error updating messages: {e}")
            # await conn.rollback()

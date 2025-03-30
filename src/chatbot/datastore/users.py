"""
users.py
---

A separate Users table for storing user information
and authentication related data.
"""

from typing import Any, Dict, Optional

from psycopg import sql  # Wrap every query as sql.SQL object for extra safety
from psycopg_pool import AsyncConnectionPool


async def create_users_table(pool: AsyncConnectionPool):
    """Create users table if not exists"""
    create_table_sql = sql.SQL("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            hashed_password VARCHAR(255),
            disabled BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            oauth_provider VARCHAR(50),
            oauth_id VARCHAR(255)
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    async with pool.connection() as conn:
        await conn.execute(create_table_sql)


async def get_user(
    pool: AsyncConnectionPool, username: str
) -> Optional[Dict[str, Any]]:
    """Get user by username"""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            sql.SQL("SELECT * FROM users WHERE username = %s"), (username,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "full_name": row[3],
                "hashed_password": row[4],
                "disabled": row[5],
                "created_at": row[6],
                "oauth_provider": row[7],
                "oauth_id": row[8],
            }
        return None


async def get_user_by_email(
    pool: AsyncConnectionPool, email: str
) -> Optional[Dict[str, Any]]:
    """Get user by email"""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            sql.SQL("SELECT * FROM users WHERE email = %s"), (email,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "full_name": row[3],
                "hashed_password": row[4],
                "disabled": row[5],
                "created_at": row[6],
                "oauth_provider": row[7],
                "oauth_id": row[8],
            }
        return None


async def create_user(
    pool: AsyncConnectionPool,
    username: str,
    email: Optional[str],
    full_name: Optional[str],
    hashed_password: Optional[str],
    oauth_provider: Optional[str] = None,
    oauth_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create new user"""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            sql.SQL("""
            INSERT INTO users 
                (username, email, full_name, hashed_password, oauth_provider, oauth_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """),
            (username, email, full_name, hashed_password, oauth_provider, oauth_id),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "full_name": row[3],
                "hashed_password": row[4],
                "disabled": row[5],
                "created_at": row[6],
                "oauth_provider": row[7],
                "oauth_id": row[8],
            }
        return {}

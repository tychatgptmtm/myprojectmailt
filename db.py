import os
from contextlib import contextmanager

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Не найден DATABASE_URL")


@contextmanager
def get_connection():
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS mailboxes (
                    user_id BIGINT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    address TEXT NOT NULL,
                    password TEXT NOT NULL,
                    token TEXT NOT NULL,
                    last_seen_message_id TEXT
                )
                """
            )
        conn.commit()


def save_mailbox(user_id: int, account_id: str, address: str, password: str, token: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mailboxes (
                    user_id, account_id, address, password, token, last_seen_message_id
                )
                VALUES (%s, %s, %s, %s, %s, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    account_id = EXCLUDED.account_id,
                    address = EXCLUDED.address,
                    password = EXCLUDED.password,
                    token = EXCLUDED.token
                """
                ,
                (user_id, account_id, address, password, token),
            )
        conn.commit()


def get_mailbox(user_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT account_id, address, password, token, last_seen_message_id
                FROM mailboxes
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {
        "account_id": row[0],
        "address": row[1],
        "password": row[2],
        "token": row[3],
        "last_seen_message_id": row[4],
    }


def update_last_seen_message(user_id: int, message_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mailboxes
                SET last_seen_message_id = %s
                WHERE user_id = %s
                """,
                (message_id, user_id),
            )
        conn.commit()


def get_all_mailboxes():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, account_id, address, password, token, last_seen_message_id
                FROM mailboxes
                """
            )
            rows = cur.fetchall()

    return [
        {
            "user_id": row[0],
            "account_id": row[1],
            "address": row[2],
            "password": row[3],
            "token": row[4],
            "last_seen_message_id": row[5],
        }
        for row in rows
    ]


def delete_mailbox(user_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM mailboxes WHERE user_id = %s",
                (user_id,),
            )
        conn.commit()            "password": row[3],
            "token": row[4],
            "last_seen_message_id": row[5],
        }
        for row in rows
    ]


def delete_mailbox(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM mailboxes WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

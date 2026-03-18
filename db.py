import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().with_name("mailboxes.db")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mailboxes (
                user_id INTEGER PRIMARY KEY,
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
        conn.execute(
            """
            INSERT INTO mailboxes (
                user_id, account_id, address, password, token, last_seen_message_id
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                account_id=excluded.account_id,
                address=excluded.address,
                password=excluded.password,
                token=excluded.token
            """,
            (user_id, account_id, address, password, token),
        )
        conn.commit()


def get_mailbox(user_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT account_id, address, password, token, last_seen_message_id
            FROM mailboxes
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

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
        conn.execute(
            """
            UPDATE mailboxes
            SET last_seen_message_id = ?
            WHERE user_id = ?
            """,
            (message_id, user_id),
        )
        conn.commit()


def get_all_mailboxes():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, account_id, address, password, token, last_seen_message_id
            FROM mailboxes
            """
        ).fetchall()

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
        conn.execute("DELETE FROM mailboxes WHERE user_id = ?", (user_id,))
        conn.commit()

import sqlite3

DB_NAME = "mailbot.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS mailboxes (
            user_id INTEGER PRIMARY KEY,
            account_id TEXT NOT NULL,
            address TEXT NOT NULL,
            password TEXT NOT NULL,
            token TEXT NOT NULL,
            last_seen_message_id TEXT
        )
        '''
    )

    cur.execute("PRAGMA table_info(mailboxes)")
    columns = [row[1] for row in cur.fetchall()]
    if "last_seen_message_id" not in columns:
        cur.execute("ALTER TABLE mailboxes ADD COLUMN last_seen_message_id TEXT")

    conn.commit()
    conn.close()


def save_mailbox(user_id: int, account_id: str, address: str, password: str, token: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT last_seen_message_id FROM mailboxes WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    last_seen = row[0] if row else None

    cur.execute(
        '''
        INSERT INTO mailboxes (user_id, account_id, address, password, token, last_seen_message_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            account_id=excluded.account_id,
            address=excluded.address,
            password=excluded.password,
            token=excluded.token
        ''',
        (user_id, account_id, address, password, token, last_seen),
    )
    conn.commit()
    conn.close()


def get_mailbox(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT account_id, address, password, token, last_seen_message_id FROM mailboxes WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

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
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE mailboxes SET last_seen_message_id=? WHERE user_id=?",
        (message_id, user_id),
    )
    conn.commit()
    conn.close()


def get_all_mailboxes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, account_id, address, password, token, last_seen_message_id FROM mailboxes"
    )
    rows = cur.fetchall()
    conn.close()

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
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM mailboxes WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

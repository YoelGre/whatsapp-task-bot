import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def connect():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    # Not strictly needed anymore – we created the tables via Supabase SQL editor
    pass

def guess_timezone(phone):
    phone = str(phone).strip()
    if phone.startswith("whatsapp:"):
        phone = phone.replace("whatsapp:", "")
    if phone.startswith("+972"):
        return "Asia/Jerusalem"
    elif phone.startswith("+1"):
        return "America/New_York"
    elif phone.startswith("+44"):
        return "Europe/London"
    elif phone.startswith("+49"):
        return "Europe/Berlin"
    elif phone.startswith("+33"):
        return "Europe/Paris"
    elif phone.startswith("+39"):
        return "Europe/Rome"
    elif phone.startswith("+91"):
        return "Asia/Kolkata"
    else:
        return "UTC"

def get_or_create_user(phone):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE phone = %s", (phone,))
            row = cur.fetchone()
            if row:
                return row["id"], False
            tz = guess_timezone(phone)
            cur.execute("INSERT INTO users (phone, timezone) VALUES (%s, %s) RETURNING id", (phone, tz))
            user_id = cur.fetchone()["id"]
            conn.commit()
            return user_id, True

def get_user_timezone(phone):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone FROM users WHERE phone = %s", (phone,))
            row = cur.fetchone()
            return row["timezone"] if row else "UTC"

def set_user_timezone(phone, timezone):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET timezone = %s WHERE phone = %s", (timezone, phone))
            conn.commit()

def get_user_id_by_phone(phone):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE phone = %s", (phone,))
            row = cur.fetchone()
            return row["id"] if row else None

def get_tasks_for_user(user_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, done, deadline FROM tasks WHERE user_id = %s ORDER BY id", (user_id,))
            return cur.fetchall()

def add_task(user_id, name, deadline=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tasks (user_id, name, deadline) VALUES (%s, %s, %s)", (user_id, name, deadline))
            conn.commit()

def mark_task_done(task_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE tasks SET done = TRUE WHERE id = %s", (task_id,))
            conn.commit()

def add_web_task(user_id, name, deadline):
    add_task(user_id, name, deadline)

def mark_web_task_done(user_id, task_id):
    mark_task_done(task_id)

def get_tasks_for_user_id(user_id):
    return get_tasks_for_user(user_id)

def remove_web_done_tasks(user_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE user_id = %s AND done = TRUE", (user_id,))
            conn.commit()

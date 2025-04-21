import sqlite3
import pytz

def guess_timezone(phone):
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

DB_FILE = "tasks.db"

def connect():
    return sqlite3.connect(DB_FILE)

def init_db():
    with connect() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                phone TEXT UNIQUE,
                timezone TEXT
            )
        ''')
        # Also update tasks table if not already created
        c.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                name TEXT,
                done INTEGER DEFAULT 0,
                deadline TEXT,
                reminded INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

def get_or_create_user(phone):
    with connect() as conn:
        c = conn.cursor()
        c.execute('SELECT id, timezone FROM users WHERE phone = ?', (phone,))
        row = c.fetchone()
        if row:
            return row[0], False  # existing user
        tz = guess_timezone(phone)
        c.execute('INSERT INTO users (phone, timezone) VALUES (?, ?)', (phone, tz))
        conn.commit()
        return c.lastrowid, True  # new user

def get_user_timezone(phone):
    with connect() as conn:
        c = conn.cursor()
        c.execute('SELECT timezone FROM users WHERE phone = ?', (phone,))
        row = c.fetchone()
        return row[0] if row else "UTC"

def set_user_timezone(phone, timezone):
    with connect() as conn:
        c = conn.cursor()
        c.execute('UPDATE users SET timezone = ? WHERE phone = ?', (timezone, phone))
        conn.commit()

def get_tasks_for_user(user_id):
    with connect() as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, done, deadline FROM tasks WHERE user_id = ?', (user_id,))
        return c.fetchall()

def add_task(user_id, name, deadline=None):
    with connect() as conn:
        c = conn.cursor()
        c.execute('INSERT INTO tasks (user_id, name, deadline) VALUES (?, ?, ?)', (user_id, name, deadline))
        conn.commit()

def mark_task_done(task_id):
    with connect() as conn:
        c = conn.cursor()
        c.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
        conn.commit()

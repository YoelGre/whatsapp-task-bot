import sqlite3

DB_FILE = "tasks.db"

def connect():
    return sqlite3.connect(DB_FILE)

def init_db():
    with connect() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE)')
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
        c.execute('SELECT id FROM users WHERE phone = ?', (phone,))
        row = c.fetchone()
        if row:
            return row[0]
        c.execute('INSERT INTO users (phone) VALUES (?)', (phone,))
        conn.commit()
        return c.lastrowid

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

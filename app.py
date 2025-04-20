from flask import Flask, request, render_template, redirect, url_for
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from threading import Thread
from datetime import datetime, timedelta
import os
import time
import json

app = Flask(__name__)
TASKS_FILE = "tasks.json"


def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    return []


def save_tasks():
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, default=str)


tasks = load_tasks()

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")
TO_NUMBER = os.environ.get("YOUR_WHATSAPP_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
SITE_URL = "https://whatsapp-task-bot.onrender.com"


def parse_flexible_date(text):
    """Support: DD-MM, DD-MM-YYYY, DD-MM HH:MM, DD-MM-YYYY HH:MM"""
    text = text.strip()
    now = datetime.now()

    formats = [
        ("%d-%m-%Y %H:%M", True),
        ("%d-%m-%Y", False),
        ("%d-%m %H:%M", True),
        ("%d-%m", False),
    ]

    for fmt, has_time in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=now.year)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
            return dt.strftime("%Y-%m-%d %H:%M") if has_time else dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_deadline(text):
    if '/due' in text:
        parts = text.split('/due')
        task_name = parts[0].strip()
        deadline = parse_flexible_date(parts[1].strip())
        return task_name, deadline
    return text.strip(), None


@app.route("/whatsapp", methods=['POST'])
def whatsapp():
    incoming_msg = request.form.get('Body').strip()
    response = MessagingResponse()
    msg = response.message()

    if incoming_msg.lower() == 'list':
        if not tasks:
            msg.body(f"No tasks yet.\nManage online: {SITE_URL}")
        else:
            lines = []
            for i, t in enumerate(tasks):
                line = f"{i+1}. {'✅' if t['done'] else '❌'} {t['name']}"
                if t['deadline']:
                    line += f" (due {t['deadline']})"
                lines.append(line)
            lines.append(f"\n🔗 Manage tasks online:\n{SITE_URL}")
            msg.body("\n".join(lines))

    elif incoming_msg.lower().startswith('done '):
        try:
            idx = int(incoming_msg[5:]) - 1
            if 0 <= idx < len(tasks):
                tasks[idx]['done'] = True
                save_tasks()
                msg.body(f"Marked task {idx+1} as done!")
            else:
                msg.body("Invalid task number.")
        except ValueError:
            msg.body("Use: done [task number]")

    else:
        name, deadline = parse_deadline(incoming_msg)
        tasks.append({'name': name, 'done': False, 'deadline': deadline, 'reminded': False})
        save_tasks()
        reply = f"Added task: {name}"
        if deadline:
            reply += f" (due {deadline})"
        msg.body(reply)

    return str(response)


@app.route("/", methods=["GET", "POST"])
def task_page():
    if request.method == "POST":
        name = request.form.get("task")
        due = request.form.get("due")
        if name:
            deadline = parse_flexible_date(due) if due else None
            tasks.append({'name': name, 'done': False, 'deadline': deadline, 'reminded': False})
            save_tasks()
        return redirect(url_for('task_page'))
    return render_template("tasks.html", tasks=tasks)


@app.route("/check/<int:task_id>")
def check(task_id):
    if 0 <= task_id < len(tasks):
        tasks[task_id]['done'] = True
        save_tasks()
    return redirect(url_for('task_page'))


@app.route("/remove_done")
def remove_done():
    global tasks
    tasks = [t for t in tasks if not t['done']]
    save_tasks()
    return redirect(url_for('task_page'))


def reminder_loop():
    while True:
        now = datetime.now()
        for task in tasks:
            if task['done'] or not task['deadline'] or task.get('reminded'):
                continue
            try:
                if len(task['deadline']) == 16:
                    deadline = datetime.strptime(task['deadline'], "%Y-%m-%d %H:%M")
                    if now + timedelta(hours=1) > deadline > now:
                        client.messages.create(
                            body=f"⏰ Reminder: '{task['name']}' is due at {task['deadline']}",
                            from_=FROM_NUMBER,
                            to=TO_NUMBER
                        )
                        task['reminded'] = True
                elif len(task['deadline']) == 10:
                    deadline = datetime.strptime(task['deadline'], "%Y-%m-%d")
                    if now + timedelta(days=1) > deadline > now:
                        client.messages.create(
                            body=f"⏰ Reminder: '{task['name']}' is due on {task['deadline']}",
                            from_=FROM_NUMBER,
                            to=TO_NUMBER
                        )
                        task['reminded'] = True
            except ValueError:
                continue
        save_tasks()
        time.sleep(3600)


reminder_thread = Thread(target=reminder_loop, daemon=True)
reminder_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

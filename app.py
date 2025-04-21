from db import init_db, get_or_create_user, get_tasks_for_user, add_task, mark_task_done
from db import get_user_timezone, set_user_timezone
import pytz
from flask import Flask, request, render_template, redirect, url_for, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from threading import Thread
from datetime import datetime, timedelta
import os
import time
import json

app = Flask(__name__)
init_db()
TASKS_FILE = "tasks.json"
USERS_FILE = "users.json"

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tasks():
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, default=str)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(known_users, f)

tasks = load_tasks()
known_users = load_users()

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
SITE_URL = "https://whatsapp-task-bot.onrender.com"

# ---------- SAFE DATE PARSING ----------

def parse_flexible_date(text):
    text = text.strip().lower()
    now = datetime.now()

    if text.startswith("today"):
        time_part = text[5:].strip()
        if time_part:
            try:
                t = datetime.strptime(time_part, "%H:%M").time()
                dt = datetime.combine(now.date(), t)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception as e:
                print(f"⚠️ Failed to parse 'today HH:MM': {e}")
        return now.strftime("%Y-%m-%d")

    elif text.startswith("tomorrow"):
        time_part = text[8:].strip()
        if time_part:
            try:
                t = datetime.strptime(time_part, "%H:%M").time()
                dt = datetime.combine(now.date() + timedelta(days=1), t)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception as e:
                print(f"⚠️ Failed to parse 'tomorrow HH:MM': {e}")
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

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
        except Exception as e:
            continue

    print(f"⚠️ Unrecognized date format: '{text}'")
    return None

def parse_deadline(text):
    try:
        if '/due' in text:
            parts = text.split('/due')
            task_name = parts[0].strip()
            deadline = parse_flexible_date(parts[1].strip())
            return task_name, deadline
        return text.strip(), None
    except Exception as e:
        print(f"⚠️ Deadline parsing error: {e}")
        return text.strip(), None

# ---------- WHATSAPP BOT ----------

@app.route("/whatsapp", methods=['POST'])
def whatsapp():
    incoming_msg = request.form.get('Body').strip()
    from_number = request.form.get('From')
    response = MessagingResponse()
    msg = response.message()

    user_id, is_new_user = get_or_create_user(from_number)
    
    if is_new_user:
        import pytz
    from datetime import datetime
    
    tz_name = get_user_timezone(from_number)
    tz_obj = pytz.timezone(tz_name)
    now = datetime.now(tz_obj)
    offset_str = now.strftime('%z')  # e.g., "+0300"
    offset_pretty = f"UTC{offset_str[:3]}:{offset_str[3:]}" if offset_str else "UTC"

        msg.body(f"""👋 Welcome to your personal WhatsApp Task Tracker!

    📍 Your time zone is set to: {tz_name} ({offset_pretty})
    ⏰ Use /due with dates like: today 14:00 or 22-04 18:00
    🌍 To change your time zone, send: tz Europe/London

    Other commands:
    • list — show tasks
    • done 1 — mark task 1 as done
    • Manage online: {SITE_URL}/{from_number}""")

        return Response(str(response), mimetype="application/xml")
    
        print(f"📩 Incoming from {from_number}: {incoming_msg}")

    if incoming_msg.lower() == "list":
        tasks = get_tasks_for_user(user_id)
        if not tasks:
            msg.body(f"No tasks yet.\nManage online: {SITE_URL}/{from_number}")
        else:
            lines = []
            for i, (task_id, name, done, deadline) in enumerate(tasks):
                line = f"{i+1}. {'✅' if done else '❌'} {name}"
                if deadline:
                    line += f" (due {deadline})"
                lines.append(line)
            lines.append(f"🔗 Manage online: {SITE_URL}/{from_number}")
            msg.body("\n".join(lines))

    elif incoming_msg.lower().startswith('done '):
        try:
            idx = int(incoming_msg[5:]) - 1
            tasks = get_tasks_for_user(user_id)
            if 0 <= idx < len(tasks):
                task_id = tasks[idx][0]
                mark_task_done(task_id)
                msg.body(f"Marked task {idx+1} as done!")
            else:
                msg.body("Invalid task number.")
        except ValueError:
            msg.body("Use: done [task number]")

    else:
        name, deadline = parse_deadline(incoming_msg)
        add_task(user_id, name, deadline)
        reply = f"Added task: {name}"
        if deadline:
            reply += f" (due {deadline})"
        msg.body(reply)

    return Response(str(response), mimetype="application/xml")


# ---------- WEB INTERFACE PER USER ----------

@app.route("/<user_id>", methods=["GET", "POST"])
def user_tasks_page(user_id):
    if user_id not in tasks:
        tasks[user_id] = []
    if request.method == "POST":
        name = request.form.get("task")
        due = request.form.get("due")
        deadline = parse_flexible_date(due.strip()) if due else None
        if name:
            tasks[user_id].append({
                'name': name,
                'done': False,
                'deadline': deadline,
                'reminded': False
            })
            save_tasks()
        return redirect(url_for('user_tasks_page', user_id=user_id))

    user_tasks = tasks[user_id]
    return render_template("tasks.html", tasks=user_tasks, user_id=user_id)

@app.route("/<user_id>/check/<int:task_id>")
def check_task(user_id, task_id):
    if user_id in tasks and 0 <= task_id < len(tasks[user_id]):
        tasks[user_id][task_id]['done'] = True
        save_tasks()
    return redirect(url_for('user_tasks_page', user_id=user_id))

@app.route("/<user_id>/remove_done")
def remove_done_tasks(user_id):
    if user_id in tasks:
        tasks[user_id] = [t for t in tasks[user_id] if not t['done']]
        save_tasks()
    return redirect(url_for('user_tasks_page', user_id=user_id))

# ---------- REMINDER THREAD ----------

def reminder_loop():
    while True:
        now = datetime.now()
        for user, user_tasks in tasks.items():
            for task in user_tasks:
                if task['done'] or not task['deadline'] or task.get('reminded'):
                    continue
                try:
                    if len(task['deadline']) == 16:
                        deadline = datetime.strptime(task['deadline'], "%Y-%m-%d %H:%M")
                        if 0 < (deadline - now).total_seconds() <= 3600:
                            try:
                                client.messages.create(
                                    body=f"⏰ Reminder: '{task['name']}' is due at {task['deadline']}",
                                    from_=FROM_NUMBER,
                                    to=user
                                )
                                print(f"📤 Reminder sent to {user}: {task['name']} (due {task['deadline']})")
                                task['reminded'] = True
                            except Exception as e:
                                print(f"❌ Failed to send reminder to {user}: {e}")
                    elif len(task['deadline']) == 10:
                        deadline = datetime.strptime(task['deadline'], "%Y-%m-%d")
                        if 0 < (deadline - now).total_seconds() <= 86400:
                            try:
                                client.messages.create(
                                    body=f"⏰ Reminder: '{task['name']}' is due on {task['deadline']}",
                                    from_=FROM_NUMBER,
                                    to=user
                                )
                                print(f"📤 Reminder sent to {user}: {task['name']} (due {task['deadline']})")
                                task['reminded'] = True
                            except Exception as e:
                                print(f"❌ Failed to send reminder to {user}: {e}")
                except ValueError as e:
                    print(f"⚠️ Reminder error: {e}")
                    continue
        save_tasks()
        time.sleep(3600)

reminder_thread = Thread(target=reminder_loop, daemon=True)
reminder_thread.start()

# ---------- RUN THE APP ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

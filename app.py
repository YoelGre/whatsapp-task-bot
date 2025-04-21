from flask import Flask, request, render_template, redirect, url_for, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from threading import Thread
from datetime import datetime, timedelta
import os
import time
import json
import pytz

app = Flask(__name__)
TASKS_FILE = "tasks.json"
USERS_FILE = "users.json"

DEFAULT_TIMEZONES = {
    "+972": "Asia/Jerusalem",
    "+1": "America/New_York",
    "+44": "Europe/London",
    "+91": "Asia/Kolkata"
}

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
    return {}

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(known_users, f)

def get_user_timezone(phone):
    tz_name = known_users.get(phone, {}).get("timezone")
    if not tz_name:
        for prefix, tz in DEFAULT_TIMEZONES.items():
            if phone.startswith(prefix):
                tz_name = tz
                known_users[phone] = {"timezone": tz_name}
                save_users()
                break
        else:
            tz_name = "UTC"
            known_users[phone] = {"timezone": tz_name}
            save_users()
    return pytz.timezone(tz_name)

tasks = load_tasks()
known_users = load_users()

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
SITE_URL = "https://whatsapp-task-bot.onrender.com"

# ---------- SAFE DATE PARSING ----------

def parse_flexible_date(text, tz):
    text = text.strip().lower()
    now = datetime.now(tz)

    if text.startswith("today"):
        time_part = text[5:].strip()
        if time_part:
            try:
                t = datetime.strptime(time_part, "%H:%M").time()
                dt = tz.localize(datetime.combine(now.date(), t))
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception as e:
                print(f"⚠️ Failed to parse 'today HH:MM': {e}")
        return now.strftime("%Y-%m-%d")

    elif text.startswith("tomorrow"):
        time_part = text[8:].strip()
        if time_part:
            try:
                t = datetime.strptime(time_part, "%H:%M").time()
                dt = tz.localize(datetime.combine(now.date() + timedelta(days=1), t))
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception as e:
                print(f"⚠️ Failed to parse 'tomorrow HH:MM': {e}")
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    formats = [
        ("%d-%m-%Y %H:%M", True),
        ("%d-%m-%Y", False),
        ("%d-%m %H:%M", True),
        ("%d-%m", False),
        ("%#d-%#m-%Y", False),
        ("%#d-%#m", False)
    ]

    for fmt, has_time in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=now.year)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
            dt = tz.localize(dt)
            return dt.strftime("%Y-%m-%d %H:%M") if has_time else dt.strftime("%Y-%m-%d")
        except Exception:
            continue

    print(f"⚠️ Unrecognized date format: '{text}'")
    return None

def parse_deadline(text, tz):
    try:
        if '/due' in text:
            parts = text.split('/due')
            task_name = parts[0].strip()
            deadline = parse_flexible_date(parts[1].strip(), tz)
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

    print(f"📩 Incoming from {from_number}: {incoming_msg}")
    tz = get_user_timezone(from_number)

    if incoming_msg.lower().startswith("/timezone"):
        parts = incoming_msg.split()
        if len(parts) == 2 and parts[1] in pytz.all_timezones:
            known_users[from_number]["timezone"] = parts[1]
            save_users()
            msg.body(f"🌍 Time zone updated to: {parts[1]}")
        else:
            msg.body("❌ Invalid time zone. Please use one from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
        return Response(str(response), mimetype="application/xml")

    if from_number not in tasks:
        tasks[from_number] = []

    if from_number not in known_users:
        tz_display = get_user_timezone(from_number).zone
        msg.body(f"👋 Welcome to your personal WhatsApp Task Tracker!

Your default time zone is {tz_display} based on your number.
To change it, type: /timezone Your/City

You can:
• Add tasks: Buy milk /due today 15:30
• Use: list / done 1
• Manage online: {SITE_URL}/{from_number}")
        print(f"🤖 Bot reply: {msg.body}")
        return Response(str(response), mimetype="application/xml")

    user_tasks = tasks[from_number]

    if incoming_msg.lower() == 'list':
        if not user_tasks:
            msg.body(f"No tasks yet.\nManage online: {SITE_URL}/{from_number}")
        else:
            lines = []
            for i, t in enumerate(user_tasks):
                line = f"{i+1}. {'✅' if t['done'] else '❌'} {t['name']}"
                if t['deadline']:
                    line += f" (due {datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M' if len(t['deadline']) > 10 else '%Y-%m-%d').strftime('%d-%m-%Y %H:%M' if len(t['deadline']) > 10 else '%d-%m-%Y')})"
                lines.append(line)
            lines.append(f"🔗 Manage online: {SITE_URL}/{from_number}")
            msg.body("\n".join(lines))

    elif incoming_msg.lower().startswith('done '):
        try:
            idx = int(incoming_msg[5:]) - 1
            if 0 <= idx < len(user_tasks):
                user_tasks[idx]['done'] = True
                tasks[from_number] = user_tasks
                save_tasks()
                msg.body(f"Marked task {idx+1} as done!")
            else:
                msg.body("Invalid task number.")
        except ValueError:
            msg.body("Use: done [task number]")

    else:
        name, deadline = parse_deadline(incoming_msg, tz)
        user_tasks.append({'name': name, 'done': False, 'deadline': deadline, 'reminded': False})
        tasks[from_number] = user_tasks
        save_tasks()
        reply = f"Added task: {name}"
        if deadline:
            display = datetime.strptime(deadline, '%Y-%m-%d %H:%M' if len(deadline) > 10 else '%Y-%m-%d').strftime('%d-%m-%Y %H:%M' if len(deadline) > 10 else '%d-%m-%Y')
            reply += f" (due {display})"
        msg.body(reply)

    print(f"🤖 Bot reply: {msg.body}")
    return Response(str(response), mimetype="application/xml")

# ---------- WEB INTERFACE PER USER ----------

@app.route("/<user_id>", methods=["GET", "POST"])
def user_tasks_page(user_id):
    if user_id not in tasks:
        tasks[user_id] = []
    if request.method == "POST":
        name = request.form.get("task")
        due = request.form.get("due")
        tz = get_user_timezone(user_id)
        deadline = parse_flexible_date(due.strip(), tz) if due else None
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
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        for user, user_tasks in tasks.items():
            tz = get_user_timezone(user)
            now = now_utc.astimezone(tz)
            for task in user_tasks:
                if task['done'] or not task['deadline'] or task.get('reminded'):
                    continue
                try:
                    fmt = "%Y-%m-%d %H:%M" if len(task['deadline']) == 16 else "%Y-%m-%d"
                    deadline = datetime.strptime(task['deadline'], fmt)
                    deadline = tz.localize(deadline) if deadline.tzinfo is None else deadline
                    delta = (deadline - now).total_seconds()
                    if (fmt == "%Y-%m-%d %H:%M" and 0 < delta <= 3600) or (fmt == "%Y-%m-%d" and 0 < delta <= 86400):
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
                except ValueError as e:
                    print(f"⚠️ Reminder error: {e}")
                    continue
        save_tasks()
        time.sleep(600)

reminder_thread = Thread(target=reminder_loop, daemon=True)
reminder_thread.start()

# ---------- RUN THE APP ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

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

@app.route("/whatsapp", methods=['POST'])
def whatsapp():
    incoming_msg = request.form.get('Body').strip()
    from_number = request.form.get('From')
    response = MessagingResponse()
    msg = response.message()

    tz = get_user_timezone(from_number)

    if incoming_msg.lower().startswith("/timezone"):
        parts = incoming_msg.split()
        if len(parts) == 2 and parts[1] in pytz.all_timezones:
            known_users[from_number]["timezone"] = parts[1]
            save_users()
            msg.body(f"Time zone updated to: {parts[1]}")
        else:
            msg.body("Invalid time zone. Please use one from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
        return Response(str(response), mimetype="application/xml")

    if from_number not in tasks:
        tasks[from_number] = []

    if from_number not in known_users:
        tz_display = get_user_timezone(from_number).zone
        msg.body(f"""Welcome to your personal WhatsApp Task Tracker!

Your default time zone is {tz_display} based on your number.
To change it, type: /timezone Your/City

You can:
- Add tasks: Buy milk /due today 15:30
- Use: list / done 1
- Manage online: {SITE_URL}/{from_number}""")
        return Response(str(response), mimetype="application/xml")

    user_tasks = tasks[from_number]

    if incoming_msg.lower() == 'list':
        if not user_tasks:
            msg.body(f"No tasks yet.\nManage online: {SITE_URL}/{from_number}")
        else:
            lines = []
            for i, t in enumerate(user_tasks):
                line = f"{i+1}. {'[Done]' if t['done'] else '[Todo]'} {t['name']}"
                if t['deadline']:
                    try:
                        fmt = '%Y-%m-%d %H:%M' if len(t['deadline']) > 10 else '%Y-%m-%d'
                        out_fmt = '%d-%m-%Y %H:%M' if len(t['deadline']) > 10 else '%d-%m-%Y'
                        line += f" (due {datetime.strptime(t['deadline'], fmt).strftime(out_fmt)})"
                    except:
                        pass
                lines.append(line)
            lines.append(f"View online: {SITE_URL}/{from_number}")
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
        name, deadline = incoming_msg.split('/due')[0].strip(), None
        if '/due' in incoming_msg:
            try:
                from datetime import datetime as dt
                deadline_text = incoming_msg.split('/due')[1].strip()
                deadline = dt.strptime(deadline_text, '%d-%m-%Y %H:%M').strftime('%Y-%m-%d %H:%M')
            except:
                deadline = None
        user_tasks.append({'name': name, 'done': False, 'deadline': deadline, 'reminded': False})
        tasks[from_number] = user_tasks
        save_tasks()
        reply = f"Added task: {name}"
        if deadline:
            try:
                fmt = '%Y-%m-%d %H:%M' if len(deadline) > 10 else '%Y-%m-%d'
                out_fmt = '%d-%m-%Y %H:%M' if len(deadline) > 10 else '%d-%m-%Y'
                reply += f" (due {datetime.strptime(deadline, fmt).strftime(out_fmt)})"
            except:
                pass
        msg.body(reply)

    return Response(str(response), mimetype="application/xml")

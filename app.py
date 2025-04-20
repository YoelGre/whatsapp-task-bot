from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from threading import Thread
from datetime import datetime, timedelta
import time

app = Flask(__name__)
tasks = []

import os

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")
TO_NUMBER = os.environ.get("YOUR_WHATSAPP_NUMBER")


client = Client(ACCOUNT_SID, AUTH_TOKEN)

def parse_deadline(text):
    if '/due' in text:
        parts = text.split('/due')
        task_name = parts[0].strip()
        try:
            deadline = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M")
            return task_name, deadline
        except ValueError:
            return task_name, None
    return text.strip(), None

@app.route("/whatsapp", methods=['POST'])
def whatsapp():
    incoming_msg = request.form.get('Body').strip()
    response = MessagingResponse()
    msg = response.message()

    # LIST TASKS
    if incoming_msg.lower() == 'list':
        if not tasks:
            msg.body("No tasks yet.")
        else:
            lines = []
            for i, t in enumerate(tasks):
                line = f"{i+1}. {'✅' if t['done'] else '❌'} {t['name']}"
                if t['deadline']:
                    line += f" (due {t['deadline'].strftime('%Y-%m-%d %H:%M')})"
                lines.append(line)
            msg.body("\n".join(lines))

    # MARK TASK DONE
    elif incoming_msg.lower().startswith('done '):
        try:
            idx = int(incoming_msg[5:]) - 1
            if 0 <= idx < len(tasks):
                tasks[idx]['done'] = True
                msg.body(f"Marked task {idx+1} as done!")
            else:
                msg.body("Invalid task number.")
        except ValueError:
            msg.body("Use: done [task number]")

    # ADD TASK (with or without deadline)
    else:
        name, deadline = parse_deadline(incoming_msg)
        tasks.append({'name': name, 'done': False, 'deadline': deadline, 'reminded': False})
        reply = f"Added task: {name}"
        if deadline:
            reply += f" (due {deadline.strftime('%Y-%m-%d %H:%M')})"
        msg.body(reply)

    return str(response)

# Reminder loop (runs in background)
def reminder_loop():
    while True:
        now = datetime.now()
        for task in tasks:
            if (
                not task['done']
                and task['deadline']
                and not task.get('reminded')
                and now + timedelta(days=1) > task['deadline']
                and now < task['deadline']
            ):
                client.messages.create(
                    body=f"⏰ Reminder: '{task['name']}' is due at {task['deadline'].strftime('%Y-%m-%d %H:%M')}",
                    from_=FROM_NUMBER,
                    to=TO_NUMBER
                )
                task['reminded'] = True
        time.sleep(3600)

reminder_thread = Thread(target=reminder_loop, daemon=True)
reminder_thread.start()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



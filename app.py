from flask import Flask, render_template
from extract import extract_timetable_data
import datetime
import os

app = Flask(__name__)

@app.route('/')
def timetable():
    pdf_path = "CSE 1st Year Section Wise.pdf"  # Ensure correct path
    section = "BE-CSE-2A"  # Hardcoded for simplicity
    timetable_data = extract_timetable_data(pdf_path, section)[1]

    # --- Notification Scheduling (FRAMEWORK ONLY) ---
    schedule_notifications(timetable_data)

    return render_template('template.html', section=section, timetable_data=timetable_data)

def schedule_notifications(timetable):
    print("--- Notification Schedule ---")
    for entry in timetable:
        day = entry['day']
        time_str = entry['time']
        subject = entry['subject']
        room = entry['room']
        raw_text = entry['raw_text']  # Access raw_text

        # --- CRITICAL: Replace this with your actual notification code! ---
        # --- This is platform-specific (Android, iOS, web) and complex. ---
        print(f"  Schedule notification for {subject} in {room or 'Unknown Room'} on {day} at {time_str} (Raw: {raw_text})")

        # --- Example (Conceptual - NOT WORKING CODE): ---
        # notification_time = calculate_notification_time(day, time_str, 5)  # 5 minutes before
        # schedule_notification(notification_time, f"Class: {subject}, Room: {room or 'Unknown'}", entry)

# def calculate_notification_time(day, time_str, minutes_before):
#     #  ---  This is where you'd do the date/time calculations ---
#     #  ---  Requires handling days of the week, current date, etc. ---
#     #  ---  This is complex and platform-dependent! ---
#     pass  # Placeholder

# def schedule_notification(time, message, data):
#     #  ---  Placeholder for platform-specific notification code ---
#     #  ---  Android:  Use a library like Plyer or native Android APIs ---
#     #  ---  iOS:      Use Plyer or native iOS APIs ---
#     #  ---  Web:      Use the Notification API (browser permissions needed) ---
#     pass  # Placeholder

if __name__ == '__main__':
    app.run(debug=True)

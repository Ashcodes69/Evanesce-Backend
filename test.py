"""
Quick standalone test to confirm Gmail SMTP sending works.
Run this from your backend folder: python test_email.py
"""
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")

# Change this to an email address you can actually check
TEST_RECIPIENT = "ns730106@gmail.com"


def send_test_email():
    if not SMTP_USER or not SMTP_APP_PASSWORD:
        print("ERROR: SMTP_USER or SMTP_APP_PASSWORD not found in .env")
        return

    msg = MIMEText("If you're reading this, evanesce's email sending works.")
    msg["Subject"] = "evanesce SMTP test"
    msg["From"] = SMTP_USER
    msg["To"] = TEST_RECIPIENT

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_APP_PASSWORD)
            server.send_message(msg)
        print(f"Success — test email sent to {TEST_RECIPIENT}")
    except smtplib.SMTPAuthenticationError as e:
        print("AUTH FAILED — check SMTP_USER and SMTP_APP_PASSWORD in .env")
        print(f"Details: {e}")
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    send_test_email()
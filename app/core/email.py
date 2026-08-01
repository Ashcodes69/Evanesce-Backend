import os
import requests
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.getenv(
    "SMTP_USER"
)  # reusing the same env var name, now holds the Brevo-verified sender


def send_email(to: str, subject: str, body: str):
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {"name": "Evanesce", "email": SENDER_EMAIL},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }

    response = requests.post(
        BREVO_API_URL, json=payload, headers=headers
    )

    if response.status_code >= 400:
        raise Exception(
            f"Brevo email send failed: {response.status_code} {response.text}"
        )

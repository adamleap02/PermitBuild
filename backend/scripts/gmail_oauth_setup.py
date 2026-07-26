"""
One-time OAuth setup to grant this project real Gmail send + read
capability for permitbuildadscharf@gmail.com, so the FOIA-reply intake
pipeline can poll for and parse incoming responses independently of
any Claude session (the Gmail MCP connector used elsewhere in this
project is tied to this chat session, not something a standalone
scheduled script can call).

Requests gmail.send (already granted previously) + gmail.readonly
(new) -- readonly means it can list/read messages and download
attachments, but cannot delete anything or modify labels.

Usage:
    venv\\Scripts\\python.exe scripts\\gmail_oauth_setup.py

This opens the default browser for a one-time consent screen (sign in as
permitbuildadscharf@gmail.com). On success, writes gmail_token.json next
to this script's parent (backend/) -- gitignored, never commit it.
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

CLIENT_SECRET_PATH = (
    r"C:\Users\schar\Downloads\client_secret_36122339988-jjn5t1dedruvcdahta6r4mkkibbuovgc.apps.googleusercontent.com.json"
)
TOKEN_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gmail_token.json")


def main():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"Saved token to {TOKEN_PATH}")
    else:
        print("Existing token is already valid.")

    # Confirm which account this actually authorized as.
    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authorized Gmail send access for: {profile['emailAddress']}")


if __name__ == "__main__":
    main()

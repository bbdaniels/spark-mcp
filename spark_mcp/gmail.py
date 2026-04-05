"""Gmail API draft creation for Personal Gmail account."""

import base64
import html
import json
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

CONFIG_DIR = Path(os.path.expanduser("~/.config/spark-mcp"))
TOKEN_PATH = CONFIG_DIR / "gmail_token.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


def _get_credentials() -> Credentials:
    """Load or refresh Gmail OAuth credentials."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"OAuth credentials not found at {CREDENTIALS_PATH}. "
                "Download your OAuth client JSON from Google Cloud Console "
                "and save it there. See README for setup instructions."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Create a draft in Personal Gmail via the Gmail API.

    Returns a summary string with the draft ID.
    """
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    # Build multipart/alternative with both plain and HTML parts.
    # Spark's draft editor rewrites plain-only drafts on first view and
    # collapses \n line breaks, so we include an HTML version that
    # preserves paragraph and line-break structure explicitly.
    html_body = _text_to_html(body)
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    message.attach(MIMEText(body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()

    draft_id = draft["id"]
    return f"Draft created (id={draft_id}). To: {to} | Subject: {subject}"


def _text_to_html(text: str) -> str:
    """Convert plain text to HTML, preserving paragraphs and auto-linking URLs.

    - Double newline -> new <p> block
    - Single newline inside a paragraph -> <br>
    - http(s) URLs become clickable <a href> links
    """
    escaped = html.escape(text)
    url_re = re.compile(r'(https?://[^\s<]+)')
    paragraphs = escaped.split("\n\n")
    parts = []
    for p in paragraphs:
        p = p.replace("\n", "<br>")
        p = url_re.sub(r'<a href="\1">\1</a>', p)
        parts.append(f'<p style="margin:0 0 12px 0">{p}</p>')
    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,'
        '\'Segoe UI\',sans-serif;font-size:14px;line-height:1.5">'
        + "".join(parts)
        + "</div>"
    )


def check_auth() -> str:
    """Check if Gmail OAuth is configured and valid."""
    if not CREDENTIALS_PATH.exists():
        return (
            f"Not configured. Download OAuth client JSON from Google Cloud Console "
            f"and save to: {CREDENTIALS_PATH}"
        )
    try:
        creds = _get_credentials()
        if creds and creds.valid:
            return "Authenticated and ready."
        return "Token exists but is not valid. Re-run auth."
    except Exception as e:
        return f"Auth error: {e}"

"""
VNSA 2.0 — Email Tool
Gmail / Outlook via IMAP (read) + SMTP (send).

Credentials live in:  backend/config/email_credentials.json
Example template:     backend/config/email_credentials.example.json

⚠  Use App Passwords (NOT your real password):
   Gmail  → myaccount.google.com/apppasswords
   Outlook → account.microsoft.com/security (App passwords)

Credential file format (JSON array, one entry per account):
[
  {
    "email":     "you@gmail.com",
    "password":  "app-password-here",
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587
  }
]

The Settings panel (index.html → Email Setup) writes this file directly.
"""

import email as _email_lib
import imaplib
import json
import smtplib
import ssl
from email.header import decode_header as _dh
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_CONFIG = Path(__file__).parent.parent / "config"
CREDS_FILE = _CONFIG / "email_credentials.json"
EXAMPLE_FILE = _CONFIG / "email_credentials.example.json"

# ── Known provider presets (auto-filled in UI) ────────────────────────────────
PROVIDER_PRESETS = {
    "gmail.com":    {"imap_host": "imap.gmail.com",    "imap_port": 993, "smtp_host": "smtp.gmail.com",    "smtp_port": 587},
    "outlook.com":  {"imap_host": "outlook.office365.com", "imap_port": 993, "smtp_host": "smtp.office365.com", "smtp_port": 587},
    "hotmail.com":  {"imap_host": "outlook.office365.com", "imap_port": 993, "smtp_host": "smtp.office365.com", "smtp_port": 587},
    "yahoo.com":    {"imap_host": "imap.mail.yahoo.com",   "imap_port": 993, "smtp_host": "smtp.mail.yahoo.com",   "smtp_port": 587},
    "icloud.com":   {"imap_host": "imap.mail.me.com",      "imap_port": 993, "smtp_host": "smtp.mail.me.com",      "smtp_port": 587},
}

# ── Tool definition (exposed to Claude) ───────────────────────────────────────
TOOL_DEFINITION = {
    "name": "email",
    "description": (
        "Read, search, and send emails via configured accounts. "
        "Requires email_credentials.json to be set up (Settings → Email Setup). "
        "Actions: list, search, read, send, accounts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action":     {"type": "string", "enum": ["list", "search", "read", "send", "accounts"],
                           "description": "list=inbox summary, search=search emails, read=full email by id, send=send email, accounts=show configured accounts"},
            "account":    {"type": "string", "description": "Email address to use (optional, uses first account if omitted)"},
            "query":      {"type": "string", "description": "Search query (subject or sender keyword)"},
            "message_id": {"type": "string", "description": "Message UID/ID for read action"},
            "to":         {"type": "string", "description": "Recipient address for send"},
            "subject":    {"type": "string", "description": "Email subject for send"},
            "body":       {"type": "string", "description": "Email body text for send"},
            "max":        {"type": "integer", "default": 10, "description": "Max emails to return for list/search"},
        },
        "required": ["action"],
    },
}


# ── Public entry point ────────────────────────────────────────────────────────

def run(action: str, account: str = "", query: str = "",
        message_id: str = "", to: str = "", subject: str = "",
        body: str = "", max: int = 10) -> str:

    creds_list = _load_creds()

    if not creds_list:
        setup_hint = (
            "No email accounts configured.\n"
            "→ Open Settings (⚙) → Email Setup and add your account.\n"
            "→ Use a Gmail App Password, not your real password.\n"
            "→ Generate one at: myaccount.google.com/apppasswords"
        )
        return setup_hint

    # Pick account
    creds = None
    if account:
        creds = next((c for c in creds_list if c.get("email", "").lower() == account.lower()), None)
    if not creds:
        creds = creds_list[0]

    if action == "accounts":
        lines = ["Configured email accounts:"]
        for c in creds_list:
            lines.append(f"  • {c.get('email', 'unknown')}  ({c.get('imap_host', '?')})")
        return "\n".join(lines)

    if action in ("list", "search"):
        return _list_or_search(creds, query, max)

    if action == "read":
        if not message_id:
            return "Provide a message_id to read."
        return _read_message(creds, message_id)

    if action == "send":
        return _send(creds, to, subject, body)

    return f"Unknown action: {action}"


# ── Credential loading ────────────────────────────────────────────────────────

def _load_creds() -> list:
    """Load email_credentials.json. Returns [] if missing or malformed."""
    if not CREDS_FILE.exists():
        return []
    try:
        data = json.loads(CREDS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        # Validate each entry has minimum required fields
        valid = []
        for entry in data:
            if (isinstance(entry, dict)
                    and entry.get("email")
                    and entry.get("password")
                    and entry.get("imap_host")
                    and entry.get("smtp_host")
                    and not entry.get("_note")):   # skip example/template entries
                valid.append(entry)
        return valid
    except Exception:
        return []


# ── IMAP helpers ──────────────────────────────────────────────────────────────

def _connect_imap(creds: dict) -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    host = creds["imap_host"]
    port = int(creds.get("imap_port", 993))
    imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    imap.login(creds["email"], creds["password"])
    return imap


def _decode_str(s) -> str:
    if not s:
        return ""
    parts = _dh(s)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return "".join(out)


def _list_or_search(creds: dict, query: str, max_results: int) -> str:
    try:
        imap = _connect_imap(creds)
        imap.select("INBOX")

        if query:
            _, msgs = imap.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        else:
            _, msgs = imap.search(None, "ALL")

        if not msgs or not msgs[0]:
            imap.logout()
            return "No messages found."

        all_ids = msgs[0].split()
        total   = len(all_ids)
        ids     = all_ids[-max_results:][::-1]   # newest first

        lines = [f"INBOX — {total} message(s). Showing {len(ids)}:"]
        for mid in ids:
            _, data = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if data and data[0]:
                raw = data[0][1] if isinstance(data[0], tuple) else b""
                msg = _email_lib.message_from_bytes(raw)
                subj = _decode_str(msg.get("Subject", "(no subject)"))[:80]
                frm  = _decode_str(msg.get("From",    ""))[:40]
                date = msg.get("Date", "")[:25]
                lines.append(f"  [{mid.decode()}] {date} | {frm} — {subj}")

        imap.logout()
        return "\n".join(lines)

    except imaplib.IMAP4.error as e:
        return f"IMAP auth error: {e}\n→ Check App Password in Settings → Email Setup."
    except Exception as e:
        return f"Email list error: {e}"


def _read_message(creds: dict, message_id: str) -> str:
    try:
        imap = _connect_imap(creds)
        imap.select("INBOX")
        _, data = imap.fetch(message_id.encode(), "(RFC822)")
        if not data or not data[0]:
            imap.logout()
            return "Message not found."

        raw = data[0][1] if isinstance(data[0], tuple) else b""
        msg = _email_lib.message_from_bytes(raw)

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if ct == "text/plain" and "attachment" not in cd:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

        imap.logout()
        return (
            f"From:    {_decode_str(msg.get('From', ''))}\n"
            f"Subject: {_decode_str(msg.get('Subject', ''))}\n"
            f"Date:    {msg.get('Date', '')}\n"
            f"{'─' * 60}\n"
            f"{body[:4000]}"
        )
    except imaplib.IMAP4.error as e:
        return f"IMAP auth error: {e}\n→ Check App Password in Settings → Email Setup."
    except Exception as e:
        return f"Email read error: {e}"


def _send(creds: dict, to: str, subject: str, body: str) -> str:
    if not to:
        return "Provide a 'to' address to send an email."
    if not subject:
        return "Provide a 'subject' for the email."
    if not body:
        return "Provide a 'body' for the email."

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = creds["email"]
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        ctx = ssl.create_default_context()
        smtp_host = creds["smtp_host"]
        smtp_port = int(creds.get("smtp_port", 587))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(creds["email"], creds["password"])
            smtp.sendmail(creds["email"], to, msg.as_string())

        return f"✅ Email sent to {to}"

    except smtplib.SMTPAuthenticationError:
        return (
            "❌ SMTP authentication failed.\n"
            "→ Make sure you're using an App Password, not your real password.\n"
            "→ Gmail: myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPRecipientsRefused:
        return f"❌ Recipient address refused: {to}"
    except Exception as e:
        return f"❌ Send failed: {e}"

"""VNSA 2.0 — Email tool (Gmail + Outlook via IMAP/SMTP)."""
import email
import imaplib
import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header as _dh
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config"
CREDS  = CONFIG / "email_credentials.json"

TOOL_DEFINITION = {
    "name": "email",
    "description": "Read, search, and send emails via configured Gmail/Outlook accounts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action":     {"type": "string", "enum": ["list", "search", "read", "send", "accounts"]},
            "account":    {"type": "string", "description": "Email address to use"},
            "query":      {"type": "string", "description": "Search query"},
            "message_id": {"type": "string"},
            "to":         {"type": "string"},
            "subject":    {"type": "string"},
            "body":       {"type": "string"},
            "max":        {"type": "integer", "default": 10},
        },
        "required": ["action"],
    },
}


def run(action: str, account: str = "", query: str = "",
        message_id: str = "", to: str = "", subject: str = "",
        body: str = "", max: int = 10) -> str:

    creds_list = _load_creds()
    if not creds_list:
        return ("No email accounts configured. "
                "Add your account via Settings → Email Setup.")

    # Pick account
    creds = None
    if account:
        creds = next((c for c in creds_list if c["email"] == account), None)
    if not creds:
        creds = creds_list[0]

    if action == "accounts":
        return "Configured: " + ", ".join(c["email"] for c in creds_list)

    if action in ("list", "search"):
        return _list_or_search(creds, query, max)

    if action == "read":
        return _read(creds, message_id)

    if action == "send":
        return _send(creds, to, subject, body)

    return f"Unknown action: {action}"


def _load_creds() -> list:
    if not CREDS.exists():
        return []
    try:
        data = json.loads(CREDS.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Filter out migration stubs
            return [c for c in data if not c.get("_migrated")]
        return []
    except Exception:
        return []


def _connect_imap(creds: dict) -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(creds["imap_host"], creds.get("imap_port", 993), ssl_context=ctx)
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
            out.append(part)
    return "".join(out)


def _list_or_search(creds: dict, query: str, max_results: int) -> str:
    try:
        imap = _connect_imap(creds)
        imap.select("INBOX")
        if query:
            _, msgs = imap.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        else:
            _, msgs = imap.search(None, "ALL")

        if not msgs[0]:
            imap.logout()
            return "No messages found."

        ids = msgs[0].split()[-max_results:][::-1]
        lines = [f"{len(msgs[0].split())} message(s) in INBOX:"]
        for mid in ids:
            _, data = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if data[0]:
                raw = data[0][1] if isinstance(data[0], tuple) else b""
                msg = email.message_from_bytes(raw)
                subj = _decode_str(msg.get("Subject", "(no subject)"))[:80]
                frm  = _decode_str(msg.get("From", ""))[:40]
                date = msg.get("Date", "")[:25]
                lines.append(f"  [{mid.decode()}] {date} | {frm} — {subj}")
        imap.logout()
        return "\n".join(lines)
    except Exception as e:
        return f"Email error: {e}"


def _read(creds: dict, message_id: str) -> str:
    try:
        imap = _connect_imap(creds)
        imap.select("INBOX")
        _, data = imap.fetch(message_id.encode(), "(RFC822)")
        if not data[0]:
            return "Message not found."
        raw = data[0][1] if isinstance(data[0], tuple) else b""
        msg = email.message_from_bytes(raw)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        imap.logout()
        return (f"From: {_decode_str(msg.get('From', ''))}\n"
                f"Subject: {_decode_str(msg.get('Subject', ''))}\n"
                f"Date: {msg.get('Date', '')}\n---\n{body[:3000]}")
    except Exception as e:
        return f"Email read error: {e}"


def _send(creds: dict, to: str, subject: str, body: str) -> str:
    if not all([to, subject, body]):
        return "Provide to, subject, and body to send an email."
    try:
        msg = MIMEMultipart()
        msg["From"]    = creds["email"]
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP(creds["smtp_host"], creds.get("smtp_port", 587)) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(creds["email"], creds["password"])
            smtp.sendmail(creds["email"], to, msg.as_string())
        return f"✅ Email sent to {to}"
    except smtplib.SMTPAuthenticationError:
        return "❌ SMTP auth failed. Check your App Password."
    except Exception as e:
        return f"❌ Send failed: {e}"

"""
VNSA 2.0 — Authentication Module
Secure session-based auth using bcrypt-hashed credentials.
Best practices: bcrypt rounds=12, constant-time comparison, no plaintext storage.
"""
import json
import secrets
from pathlib import Path

# Try passlib first (preferred), fall back to bcrypt directly
try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    def _hash(password: str) -> str:
        return _pwd_context.hash(password)
    def _verify(plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)
except ImportError:
    import bcrypt as _bcrypt
    def _hash(password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()
    def _verify(plain: str, hashed: str) -> bool:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())

CONFIG_DIR   = Path(__file__).parent
CREDS_FILE   = CONFIG_DIR / ".vnsa_auth.json"   # hidden file, never committed
SESSION_FILE = CONFIG_DIR / ".session_secret"    # random session secret


# ── Session secret ────────────────────────────────────────────────────────────

def get_session_secret() -> str:
    """Return persistent session secret, generating one if absent."""
    if SESSION_FILE.exists():
        s = SESSION_FILE.read_text().strip()
        if len(s) >= 32:
            return s
    s = secrets.token_hex(32)
    SESSION_FILE.write_text(s)
    SESSION_FILE.chmod(0o600)
    return s


# ── Credential management ─────────────────────────────────────────────────────

def credentials_exist() -> bool:
    """Return True if VNSA credentials have been set up."""
    if not CREDS_FILE.exists():
        return False
    try:
        data = json.loads(CREDS_FILE.read_text())
        return bool(data.get("username_hash") and data.get("password_hash"))
    except Exception:
        return False


def setup_credentials(username: str, password: str) -> bool:
    """
    Hash and store credentials. Called once at first setup.
    Returns True on success.
    """
    try:
        data = {
            "username_hash": _hash(username),
            "password_hash":  _hash(password),
        }
        CREDS_FILE.write_text(json.dumps(data, indent=2))
        CREDS_FILE.chmod(0o600)   # owner read/write only
        return True
    except Exception:
        return False


def verify_credentials(username: str, password: str) -> bool:
    """
    Verify username + password against stored hashes.
    Constant-time: always checks both to prevent timing attacks.
    """
    if not CREDS_FILE.exists():
        return False
    try:
        data = json.loads(CREDS_FILE.read_text())
        u_ok = _verify(username, data.get("username_hash", ""))
        p_ok = _verify(password, data.get("password_hash", ""))
        return u_ok and p_ok
    except Exception:
        return False


def change_credentials(old_username: str, old_password: str,
                       new_username: str, new_password: str) -> bool:
    """Change credentials after verifying the old ones."""
    if not verify_credentials(old_username, old_password):
        return False
    return setup_credentials(new_username, new_password)

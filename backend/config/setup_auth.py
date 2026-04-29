"""
VNSA 2.0 — One-time credential bootstrap.
Run this ONCE to hash and store Reaver's credentials securely.
Usage: python backend/config/setup_auth.py
"""
from auth import setup_credentials, credentials_exist

USERNAME = "reaveratlas@gmail.com"
PASSWORD = "Marmar@160999"

if credentials_exist():
    print("[AUTH] Credentials already configured. Use change_credentials() to update.")
else:
    ok = setup_credentials(USERNAME, PASSWORD)
    if ok:
        print("[AUTH] Credentials hashed and stored securely.")
    else:
        print("[AUTH] Failed to store credentials.")

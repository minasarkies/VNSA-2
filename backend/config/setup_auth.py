"""
VNSA 2.0 — Credential Bootstrap (Interactive)
Run this once to create hashed credentials for the VNSA login screen.
Usage: python backend/config/setup_auth.py

NEVER hardcode credentials in this file.
"""
import getpass
import sys
from pathlib import Path

# Allow running from project root or from backend/config/
sys.path.insert(0, str(Path(__file__).parent))

try:
    from auth import setup_credentials, credentials_exist, change_credentials
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config.auth import setup_credentials, credentials_exist, change_credentials


def main():
    print("VNSA 2.0 — Credential Setup")
    print("=" * 40)

    if credentials_exist():
        print("\n[!] Credentials already configured.")
        choice = input("Change them? (y/N): ").strip().lower()
        if choice != "y":
            print("Aborted.")
            return

        print("\nEnter CURRENT credentials to verify:")
        old_user = input("  Current username: ").strip()
        old_pass = getpass.getpass("  Current password: ")

        print("\nEnter NEW credentials:")
        new_user = input("  New username: ").strip()
        new_pass = getpass.getpass("  New password: ")
        new_pass2 = getpass.getpass("  Confirm new password: ")

        if new_pass != new_pass2:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

        if change_credentials(old_user, old_pass, new_user, new_pass):
            print("\n[OK] Credentials updated successfully.")
        else:
            print("\nERROR: Could not update — old credentials incorrect.")
            sys.exit(1)
    else:
        print("\nFirst-time setup. Enter credentials for VNSA login:\n")
        username = input("  Username (e.g. your email): ").strip()
        if not username:
            print("ERROR: Username cannot be empty.")
            sys.exit(1)

        password = getpass.getpass("  Password: ")
        password2 = getpass.getpass("  Confirm password: ")

        if password != password2:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

        if len(password) < 6:
            print("ERROR: Password must be at least 6 characters.")
            sys.exit(1)

        if setup_credentials(username, password):
            print("\n[OK] Credentials stored securely (bcrypt hashed).")
            print("     You can now launch VNSA normally.")
        else:
            print("\nERROR: Failed to store credentials.")
            sys.exit(1)


if __name__ == "__main__":
    main()

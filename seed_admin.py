"""One-time script: creates a single admin account in whatever database
DATABASE_URL points at, using BOOTSTRAP_ADMIN_USERNAME/BOOTSTRAP_ADMIN_PASSWORD
from the environment. Meant to be run once against a fresh, empty production
database so there's a way to log in and add the rest of the team through the
Team Overview page afterward — production starts with no roster at all, so
without this there's no way in.

This is a manual, run-it-yourself script, not an automatic boot-time feature
— nothing in app.py calls this. Refuses to run if the roster already has
anyone in it, so it can never be used to inject a second/rogue account later;
run it again after that and it just exits without changing anything.

Run with, e.g.:
    BOOTSTRAP_ADMIN_USERNAME=admin BOOTSTRAP_ADMIN_PASSWORD=... py seed_admin.py
No password is hardcoded here on purpose, so this file is safe to commit —
supply the real one via the environment each time you actually run it.
"""
import os
import uuid

from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import generate_password_hash

import db


def main():
    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    if not password:
        raise SystemExit(
            "Set BOOTSTRAP_ADMIN_PASSWORD (and optionally BOOTSTRAP_ADMIN_USERNAME) "
            "in the environment before running this."
        )

    db.init_db()
    roster = db.load_roster()
    if roster:
        raise SystemExit(
            f"Roster already has {len(roster)} account(s) — refusing to seed a "
            "duplicate admin. Use the Team Overview page to add accounts instead."
        )

    roster.append({
        "id": str(uuid.uuid4())[:8],
        "name": "Admin",
        "role": "admin",
        "username": username,
        "password_hash": generate_password_hash(password),
        "email": None,
    })
    db.save_roster(roster)
    print(f"Created admin account — username: {username}")


if __name__ == "__main__":
    main()

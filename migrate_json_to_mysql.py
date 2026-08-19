"""One-time migration: load the old data/*.json files and write them into
MySQL via db.py. Safe to re-run — it always overwrites the MySQL tables with
whatever is currently in the JSON files (matches db.save_x()'s
replace-the-whole-table semantics), so re-running after the JSON files
haven't changed is a no-op in effect.

Run with: py migrate_json_to_mysql.py
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

import db

DATA_DIR = "data"


def _load_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    db.init_db()

    roster = _load_json("roster.json")
    reports = _load_json("reports.json")
    projects = _load_json("projects.json")
    changes = _load_json("changes.json")

    db.save_roster(roster)
    db.save_reports(reports)
    db.save_projects(projects)
    db.save_changes(changes)

    print(f"Migrated: {len(roster)} roster member(s), {len(reports)} report(s), "
          f"{len(projects)} project(s), {len(changes)} change(s) into MySQL.")


if __name__ == "__main__":
    main()

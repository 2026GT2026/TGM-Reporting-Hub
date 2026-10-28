"""Bulk import of To Do entries from a JSON file (default: import_todos_data.json).

Used by the "Import To Do" page in Reportly, and also runnable by hand:

    python import_todos.py --dry-run     # print what would happen, change nothing
    python import_todos.py               # do it, in one transaction

Every row is saved the way the "Insert To Do" form saves one (same columns, same
formats): Completed, starts 9:00 AM, Duration chosen so Expected End is the day's
end time, default priority, hours and comment left empty.

Safe to run twice: an entry that already exists with the same text, start date
and project is skipped. Existing To Dos are never touched.
"""

import argparse
import json
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import db  # noqa: E402  (needs DATABASE_URL from .env first)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "import_todos_data.json")

PERSON = "Chiamaka"
PROJECT_NAME = "TGM Enterprise"
OLD_PROJECT_NAME = "Application Hub (Application Dashboard)"
START_TIME = "09:00"
WORK_START_HOUR = 9               # same 9am-5pm workday app.py uses for Expected End
DEFAULT_PRIORITY = "Immediate"    # the form's default (first item of TODO_PRIORITIES in app.py)


def validate(days):
    """Checks the shape of the file; raises ValueError with a plain message."""
    if not isinstance(days, list) or not days:
        raise ValueError("The file should be a list of days.")
    for d in days:
        if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
            raise ValueError("Each day needs a date, an end_time and a list of entries.")
        try:
            datetime.strptime(d.get("date", ""), "%Y-%m-%d")
            end = datetime.strptime(d.get("end_time", ""), "%H:%M")
        except ValueError:
            raise ValueError(f"Day {d.get('date')!r}: date must be YYYY-MM-DD and end_time HH:MM.")
        if end.hour <= WORK_START_HOUR or end.hour > 17:
            raise ValueError(f"Day {d['date']}: end_time must be after 09:00 and no later than 17:00.")
        for e in d["entries"]:
            if not isinstance(e, dict) or not str(e.get("task", "")).strip():
                raise ValueError(f"Day {d['date']}: every entry needs a non-empty task.")


TEMPLATE_HEADERS = ["Date", "End Time", "User View", "What Is To Be Done", "Justification", "Notes"]


def _cell_date(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v or "").strip()


def _cell_time(v):
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    t = str(v or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(t.upper(), fmt).strftime("%H:%M")
        except ValueError:
            pass
    return t


def days_from_xlsx(file_obj):
    """Reads the Excel template into the same list-of-days shape the JSON uses.
    Rows with the same Date and End Time are grouped into one day, in order."""
    import openpyxl
    ws = openpyxl.load_workbook(file_obj, data_only=True).active
    header = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    want = [h.lower() for h in TEMPLATE_HEADERS]
    missing = [h for h in TEMPLATE_HEADERS if h.lower() not in header]
    if missing:
        raise ValueError("The first row must have these columns: " + ", ".join(TEMPLATE_HEADERS)
                         + ". Missing: " + ", ".join(missing) + ".")
    idx = {w: header.index(w) for w in want}
    days, by_key = [], {}
    for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(c not in (None, "") for c in row):
            continue
        get = lambda name: row[idx[name.lower()]] if idx[name.lower()] < len(row) else None
        date, end = _cell_date(get("Date")), _cell_time(get("End Time"))
        key = (date, end)
        if key not in by_key:
            by_key[key] = {"date": date, "end_time": end, "entries": []}
            days.append(by_key[key])
        text = lambda name: str(get(name) or "").strip()
        by_key[key]["entries"].append({
            "user_view": text("User View"), "task": text("What Is To Be Done"),
            "justification": text("Justification"), "notes": text("Notes"),
        })
    return days


def build_rows(days, project_id, assignee=PERSON, added_by=PERSON):
    now = datetime.now().isoformat()
    rows = []
    for day in days:
        end_hour = int(day["end_time"].split(":")[0])
        duration = float(end_hour - WORK_START_HOUR)   # 9:00 + 7h = 4 PM, + 8h = 5 PM
        for e in day["entries"]:
            rows.append({
                "id": str(uuid.uuid4())[:8],
                "project_id": project_id,
                "task": e["task"].strip(),
                "assignee": assignee,
                "start_date": day["date"],
                "start_time": START_TIME,
                "duration_hours": duration,
                "comment": "",
                "notes": e.get("notes", "").strip(),
                "status": "Completed",
                "completed_date": day["date"],
                "completed_time": day["end_time"],
                "priority": DEFAULT_PRIORITY,
                "user_view": e.get("user_view", "").strip(),
                "hours_estimate": None,
                "hours_estimate_approved": 0,
                "hours_actual": None,
                "justification": e.get("justification", "").strip(),
                "added_by": added_by,
                "added_at": now,
                "edited_by": None,
                "edited_at": None,
            })
    return rows


def import_rows(cur, rows, dry_run=False):
    """Inserts the rows not already there. Returns (new_rows, skipped_rows).
    Runs inside the caller's transaction."""
    cols = ", ".join(db.TODOS_COLUMNS)
    marks = ", ".join(["%s"] * len(db.TODOS_COLUMNS))
    insert_sql = f"INSERT INTO todos ({cols}) VALUES ({marks})"
    new, skipped = [], []
    for r in rows:
        cur.execute(
            "SELECT id FROM todos WHERE task=%s AND start_date=%s AND project_id=%s",
            (r["task"], r["start_date"], r["project_id"]),
        )
        if cur.fetchone():
            skipped.append(r)
            continue
        new.append(r)
        if not dry_run:
            cur.execute(insert_sql, tuple(r[c] for c in db.TODOS_COLUMNS))
    return new, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print only, change nothing")
    args = ap.parse_args()

    with open(DATA_FILE, encoding="utf-8") as f:
        days = json.load(f)
    validate(days)

    with db._db() as (conn, cur):
        cur.execute("SELECT name FROM roster WHERE name=%s", (PERSON,))
        if not cur.fetchone():
            raise SystemExit(f"Team member '{PERSON}' not found. Nothing changed.")

        cur.execute("SELECT id, name FROM projects WHERE name=%s", (PROJECT_NAME,))
        proj = cur.fetchone()
        rename = False
        if not proj:
            cur.execute("SELECT id, name FROM projects WHERE name=%s", (OLD_PROJECT_NAME,))
            proj = cur.fetchone()
            rename = True
        if not proj:
            raise SystemExit(f"Neither '{PROJECT_NAME}' nor '{OLD_PROJECT_NAME}' found. Nothing changed.")

        if rename:
            print(f"Project {proj['id']}: rename '{OLD_PROJECT_NAME}' -> '{PROJECT_NAME}'")
            if not args.dry_run:
                cur.execute("UPDATE projects SET name=%s WHERE id=%s", (PROJECT_NAME, proj["id"]))
        else:
            print(f"Project {proj['id']}: already named '{PROJECT_NAME}'")

        rows = build_rows(days, proj["id"])
        new, skipped = import_rows(cur, rows, args.dry_run)
        for r in new:
            print(f"  {'would add' if args.dry_run else 'add'}  {r['start_date']} 09:00 -> {r['completed_time']}"
                  f"  [{r['assignee']}]  {r['task'][:60]}")
        for r in skipped:
            print(f"  skip (already there)  {r['start_date']}  {r['task'][:60]}")
        print(f"\n{'Dry run' if args.dry_run else 'Done'}: {len(rows)} in file, "
              f"{len(new)} {'would be added' if args.dry_run else 'added'}, {len(skipped)} skipped.")
    # the _db() context commits on a clean exit and rolls everything back on any error


if __name__ == "__main__":
    main()

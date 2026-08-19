"""Parses the '✅ Daily Log' sheet from the R&D tracking workbook into report
rows — the daily-log counterpart to import_projects.py's Projects parsing.
Reused by the /reports/upload route so uploading the same spreadsheet fills
in daily logs the same way dropping it into the project folder used to.

The sheet has no per-row date or ID column — each day is a header row
(". Monday, 18 May 2026") followed by a repeated "Person / What Was Done /
TO-DO" sub-header and then one row per person, until a blank row separates
it from the next day. Blank people-rows (no work logged, e.g. a holiday
where only one person left a note) are skipped, matching how the original
data was captured.
"""
import re
from datetime import datetime

from import_projects import clean_field

DAY_HEADER_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")

# The sheet uses short first names; map onto each person's full roster name.
NAME_ALIASES = {
    "Chi": "Chiamaka",
    "Totan": "Totan",
    "Victor": "Victor",
    "Dami": "Dami",
}


def find_daily_log_sheet(wb):
    for name in wb.sheetnames:
        if "daily log" in name.lower():
            return wb[name]
    raise ValueError("No sheet with 'Daily Log' in its name was found in the workbook.")


def _parse_day_header(value):
    if not value:
        return None
    m = DAY_HEADER_RE.search(str(value))
    if not m:
        return None
    day, month, year = m.groups()
    try:
        return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def import_daily_logs(wb=None, roster_names=None):
    """Returns (rows, skipped_names). `rows` is a list of
    {name, date, raw_work, raw_pending} dicts, one per person per day that
    actually has logged work. `roster_names`, if given, restricts rows to
    people with that exact (post-alias) name — anyone else found in the
    sheet is left out of `rows` and their sheet name added to
    `skipped_names` instead, so the caller can report who got skipped
    rather than silently dropping or misattributing their entries."""
    if wb is None:
        raise ValueError("import_daily_logs requires an already-open workbook")
    ws = find_daily_log_sheet(wb)

    rows = []
    skipped_names = set()
    current_date = None
    for row in ws.iter_rows(values_only=True):
        label = row[1]
        if label is None:
            continue
        label = str(label).strip()
        if label.startswith("."):
            current_date = _parse_day_header(label)
            continue
        if label == "Person" or current_date is None:
            continue

        raw_work = clean_field(row[2])
        if not raw_work:
            continue

        name = NAME_ALIASES.get(label, label)
        if roster_names is not None and name not in roster_names:
            skipped_names.add(label)
            continue

        rows.append({
            "name": name,
            "date": current_date,
            "raw_work": raw_work,
            "raw_pending": clean_field(row[3]),
        })
    return rows, sorted(skipped_names)

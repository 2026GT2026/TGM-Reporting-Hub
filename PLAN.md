# Reportly — Development Plan & Change Log

This document records every change made to the project, step by step, with the
date and time it happened, so you can understand what was done and repeat or
modify it yourself in the future. Timestamps come from the actual file edit
times during each work session (system clock), grouped into the logical change
they belonged to.

---

## Overview — How Reportly Got Here

**In the beginning (before this log starts):** Reportly was a small Flask app
called "Report Hub" that kept everything — the team roster, daily
accomplishment reports, the R&D project tracker, a change log — in four flat
JSON files on disk (`data/roster.json`, `data/reports.json`,
`data/projects.json`, `data/changes.json`). Filling in the Projects section
meant dropping an Excel tracking sheet into the project folder and running
`import_projects.py`, which parsed it straight into `data/projects.json`.
Logging in meant picking a username from the roster.

**§1 — Moved off flat files onto MySQL.** The JSON-file storage was replaced
with a real MySQL database (`db.py`), running locally for development. Every
route kept working unchanged because the new storage layer exposes the exact
same `load_x()`/`save_x()` functions the routes already called — only what's
underneath them changed. The existing JSON data (4 people, 190 reports, 19
projects) was migrated in as a one-time local dev seed.

**§2 — Renamed to Reportly.** "Report Hub" became "Reportly" everywhere
visible, with a real logo (replacing a CSS-drawn placeholder) that doubles as
the browser favicon.

**§3 — Added a "Download Everything" button**, because by this point the live
app had accumulated more up-to-date data (edited projects, months of new
daily reports) than the original spreadsheet — one export covering roster,
projects, changes, and every daily log at once.

**§4 → §7 — Rebuilt the spreadsheet-import workflow for a web app.** The old
local-folder-drop trick (drop the `.xlsx` in, run a script) doesn't work once
the app's running somewhere you don't have shell access to. §4 added an
in-app upload for Projects. Before shipping that as "done," §7 went back and
actually checked the original spreadsheet to see everything the old
local-drop method covered — turned out that spreadsheet also has a Daily Log
sheet matching Reportly's daily-reports feature exactly (confirmed: the
database's report dates line up with that sheet exactly), so the upload was
expanded to fill in both Projects *and* Daily Logs from one uploaded file,
matching and updating existing rows instead of overwriting everything.

**§5 — Decided production starts empty.** Rather than pushing the local dev
data live, production gets a blank MySQL database and gets filled in via the
§4/§7 upload feature after deploying — the local data was already a step
stale by the time this was decided, so starting clean and re-importing was
safer than guessing what to sync.

**§6 → §8 — Login identity.** §6 first considered replacing the 4 existing
accounts with fresh email-based ones, but that would have orphaned 190+
reports and every project's ownership tied to those 4 names — flagged as
pending rather than guessed at. §8 resolved it differently: email was added
as a *second* way to log in, alongside username, on the *same 4 existing
accounts* — no data orphaned, no accounts recreated.

**§9 — Made a from-scratch deployment actually possible.** With production
starting empty (§5), nobody could log in on day one — signing in requires an
existing roster account, and there'd be none. §9 adds a one-time script to
seed exactly one admin account so there's a way in, and fixes a real bug
that testing turned up: querying an empty table returned a raw database
tuple instead of a list, which crashed the very first project/report/
change/roster-member ever added to a fresh database.

**Where that leaves things today:** Reportly runs on MySQL, is branded
consistently, can export and re-import its own data via spreadsheet, logs
in by username or email, and has a working path from an empty production
database to a usable app. The sections below are the detailed, dated record
of how each of those pieces was actually built.

---

## Table of Contents

1. [MySQL Migration — Replacing the JSON Files (2026-08-17)](#1-mysql-migration--replacing-the-json-files-2026-08-17)
2. [Reportly Rebrand — Name, Logo & Favicon (2026-08-17)](#2-reportly-rebrand--name-logo--favicon-2026-08-17)
3. [Full Data Export — "Download Everything" (2026-08-18)](#3-full-data-export--download-everything-2026-08-18)
4. [Projects Spreadsheet Upload — Fill MySQL the Way the Old Local Import Did (2026-08-18)](#4-projects-spreadsheet-upload--fill-mysql-the-way-the-old-local-import-did-2026-08-18)
5. [Decision — Production Starts Blank, No Seeded Local Data (2026-08-18)](#5-decision--production-starts-blank-no-seeded-local-data-2026-08-18)
6. [Pending — Email-Based Accounts, Fresh Sign-Ups (TO BUILD)](#6-pending--email-based-accounts-fresh-sign-ups-to-build)
7. [Upload Expanded to Cover Daily Logs Too (2026-08-18)](#7-upload-expanded-to-cover-daily-logs-too-2026-08-18)
8. [Email as a Login Identifier, Added to the 4 Existing Accounts (2026-08-18)](#8-email-as-a-login-identifier-added-to-the-4-existing-accounts-2026-08-18)
9. [Bootstrap Admin Script + Empty-Database Bug Fix (2026-08-18)](#9-bootstrap-admin-script--empty-database-bug-fix-2026-08-18)

---

## 1. MySQL Migration — Replacing the JSON Files (2026-08-17)

**What it does:** Reportly used to store everything — roster, daily reports,
projects, changes — in four flat files: `data/roster.json`, `data/reports.json`,
`data/projects.json`, `data/changes.json`. Every request re-read the whole file
and every save rewrote it. This replaces that with MySQL, running locally at
first for development.

### Files involved
- `db.py` ← new file, all MySQL logic lives here
- `app.py` ← swapped the file-based `load_x()`/`save_x()` helpers for `db.py`'s
- `requirements.txt` ← added `pymysql`, `openai` (the latter was already
  imported by `app.py` but missing from requirements — pre-existing gap, fixed
  in passing)
- `.env` ← added `DATABASE_URL`
- `migrate_json_to_mysql.py` ← new file, one-time migration script

### What was done, step by step

**15:34 — `app.py` rewired to use `db.py`.** Removed the `DATA_DIR`/`*_FILE`
constants and the eight `load_x()`/`save_x()` functions that read/wrote JSON.
Replaced them with `load_roster = db.load_roster`, etc. — same call sites
throughout the route handlers, only the underlying storage changed. Added
`db.init_db()` on boot.

**15:34 — `requirements.txt` updated** to add `pymysql`.

**15:34 — `.env` updated** with
`DATABASE_URL=mysql+pymysql://root:***@localhost:3306/tgm_reporthub`, pointing
at the same local MySQL server your AppHub project already uses, in its own
separate `tgm_reporthub` database.

**15:35 — `migrate_json_to_mysql.py` written and run.** One-time script: reads
the four JSON files, calls `db.init_db()` to create tables, then
`db.save_roster()` / `save_reports()` / `save_projects()` / `save_changes()`
to load everything into MySQL. Result: **4 roster members, 190 reports, 19
projects, 0 changes** migrated and verified against direct `SELECT COUNT(*)`
queries.

**`db.py` itself** (written just before the `app.py` edit above, so its
first version predates the 15:34 timestamp): a MySQL storage layer via
`pymysql`, exposing the exact same `load_x()`/`save_x(data)` interface the
routes already called (`load` returns a list of dicts, `save` replaces the
whole table with the given list, in one transaction). Chose whole-table
replace over row-level CRUD because it let every existing route keep working
unchanged — they already load a list, mutate it, and save it back — and it's
fast enough at this scale (a handful of roster rows, ~20 projects, a few
hundred report rows). Schema: `roster`, `reports`, `projects`, `changes`
tables, all `utf8mb4`. Had to backtick-quote the `generated` column
(`` `generated` ``) since it's a MySQL 8 reserved word for generated columns.

**App verified booting against MySQL:** login page returned 200, unauthenticated
`/dashboard` correctly redirected (302), no errors in the log.

---

## 2. Reportly Rebrand — Name, Logo & Favicon (2026-08-17)

**What it does:** Renamed the app from "Report Hub" to **Reportly** everywhere
visible, and replaced the old CSS-drawn "R/h" circle mark with a real logo that
also serves as the browser favicon.

### Files involved
- `static/logo.svg` ← new file, the logo/favicon source of truth
- `templates/base.html` ← favicon link, title, sidebar logo
- `templates/login.html` ← login-page logo
- 9 other templates ← page-title text only
- `README.md`, `db.py` (docstring) ← name reference cleanup

### What was done, step by step

**15:49 — `static/logo.svg` created.** A rounded-square badge in the
existing brand gradient (`#6E2A52` → `#4A1B38`) with three ascending white
bars (report/analytics motif) and a small accent dot.

**15:50 — `templates/base.html` updated:**
- `<title>` default changed from "TGM Report Hub" to "Reportly"
- Added `<link rel="icon" type="image/svg+xml" href=".../logo.svg">`
- Removed the old `.sidebar-logo-icon` CSS (the circle + `<span class="r">`/`<span class="h">` letters)
- Added `.brand-logo` / `.brand-logo.lg` classes sized to replace it
- Sidebar mark now `<img class="brand-logo" src=".../logo.svg">`, text "Report Hub" → "Reportly"

**15:52 — `templates/login.html` updated** the same way: CSS circle → `<img class="brand-logo lg">`, "Report Hub" → "Reportly", page title → "Reportly: Sign In".

**15:52 — Remaining 9 templates' `{% block title %}` updated** (`Report Hub:` → `Reportly:`): `admin_reports.html`, `changes.html`, `change_form.html`, `dashboard.html`, `my_reports.html`, `projects.html`, `project_detail.html`, `project_form.html`, `report_edit.html`, `team.html`, `today.html`.

**15:53 — `db.py` docstring and `README.md`** updated to say "Reportly" instead of "Report Hub".

**Deliberately left alone:** `data/reports.json` and `data/projects.json` contain
literal text like *"Report Hub"* where team members wrote about **building**
the Report Hub project itself (it's project `RD-015`, and shows up in several
daily logs). Renaming those would falsify historical work records, so they
were left untouched — only branding text in templates/UI was renamed.

**Verified:** app booted, `<title>Reportly: Sign In</title>` confirmed in the
rendered login page, `static/logo.svg` served 200.

**Design note for later:** the SVG favicon renders in Chrome, Edge and
Firefox but not Safari (no SVG favicon support there — it just shows a blank
tab icon). Not fixed yet; add a PNG fallback if Safari support matters.

---

## 3. Full Data Export — "Download Everything" (2026-08-18)

**What it does:** A single `.xlsx` download containing everything currently in
Reportly — roster, projects, changes, and every daily log ever submitted — in
one workbook with four sheets. Existing exports (`Download Projects`,
`Download Changes Log`, weekly export) only ever covered one dataset each;
this is the "get the whole current state" button, specifically because the
live app now holds updates (new/edited projects, months of daily logs) that
the original spreadsheet never had — it's the more current source, so it
needed to be downloadable as one file.

### Files involved
- `app.py` ← new `/download-all` route
- `templates/team.html` ← new "Download Everything (.xlsx)" button

### What was done, step by step
Added `download_all()` (admin-only, mirrors the existing `download_projects`/
`download_changes` pattern and reuses their `styled_export_sheet()` helper).
Builds one `Workbook` with four sheets — **Roster** (name/role/username, no
password hashes), **Projects**, **Changes**, **Daily Logs** — each styled the
same as the existing single-dataset exports. Wired a "Download Everything
(.xlsx)" button into the Full Data Export card on the Team Overview page.

**Verified** via a throwaway smoke-test script (deleted after use) that drove
the route through Flask's test client with an injected admin session: 200
response, correct sheet names, and row counts matching the live data exactly
(4 roster / 19 projects / 0 changes / 190 daily logs).

---

## 4. Projects Spreadsheet Upload — Fill MySQL the Way the Old Local Import Did (2026-08-18)

**What it does:** Before MySQL, filling in project data meant dropping the R&D
tracking `.xlsx` into the project folder and running `import_projects.py`,
which parsed it straight into `data/projects.json`. With production about to
start on a blank MySQL database (see §5), that workflow needed a web
equivalent: an admin uploads the spreadsheet through the app, and it fills the
Projects table the same way — without needing shell/file access to a server
you don't control the filesystem of.

### Files involved
- `import_projects.py` ← `import_projects()` now accepts an optional already-open workbook
- `db.py` ← new `upsert_projects()`
- `app.py` ← new `/projects/upload` route
- `templates/team.html` ← new upload form

### What was done, step by step

**`import_projects.py` refactored:** `import_projects(wb=None)` — when called
with no argument it behaves exactly as before (reads `XLSX_FILE` from disk,
for the CLI script); when passed an already-loaded `wb`, it parses that
instead, so the same row-parsing logic (date/percent normalization, em-dash
stripping, sheet-detection by name) works for an in-memory uploaded file too.

**`db.upsert_projects(rows)` added:** `INSERT ... ON DUPLICATE KEY UPDATE`
keyed on `id`, rather than the wholesale-replace `save_projects()` used
elsewhere — a re-uploaded sheet must update matching projects and add new
ones without deleting projects that only exist because someone added them
through the UI. `created_at` is excluded from the `UPDATE` clause so an
existing project's original creation date survives a re-upload; every other
column (including `updated_at`) takes the sheet's value.

**`/projects/upload` route added** (admin-only, POST): reads the uploaded
file into an in-memory `openpyxl` workbook, parses it via
`parse_projects_workbook()`, and calls `db.upsert_projects()`. Flashes a
row count on success, a readable error if the file can't be parsed.

**`templates/team.html`:** new "Import Projects from Spreadsheet" card with a
file-upload form (admin-only, same as the rest of the Team Overview page).

**Verified** with the same test-client smoke test as §3, using the real
`RD_Project_Track_Updated.xlsx` already in the repo: parsed 18 rows, all 18
matched existing project IDs and were updated in place; the 19th project in
the database (`RD-019`, added directly through the UI, never in the
spreadsheet) was untouched; roster and reports counts were unaffected by the
upload, confirming it only ever touches `projects`.

---

## 5. Decision — Production Starts Blank, No Seeded Local Data (2026-08-18)

Recorded because it reverses an assumption from §1: the local MySQL migration
(the 4/190/19/0 counts) is **dev-only** and will not be pushed to production.
When Reportly deploys, its production `DATABASE_URL` points at a separate,
empty MySQL database — no `migrate_json_to_mysql.py` run against it, no
seeded rows.

**Why:** the local JSON files are a stale snapshot from whenever they were
last dropped in; the live local app (backed by the local MySQL DB) has since
accumulated edits — updated projects, new daily logs — that the original
spreadsheet doesn't have. Rather than deciding what's "current" and syncing
it once by hand, production starts empty and gets filled the same way local
data always was: by dropping in the spreadsheet — now via the §4 upload
feature instead of shell access to a `data/` folder.

**How this plays out once deployed:** first admin login on production,
upload the current `.xlsx` (or a fresh export via §3's "Download Everything"
first, to be safe) via the Team Overview page, projects fill in. Roster
accounts get created fresh through the existing "Add Member" form (see §6 —
this is also where the email-based identifier decision applies). From that
point on, production is the live system and grows on its own through normal
use — no more migration steps.

---

## 6. Pending — Email-Based Accounts, Fresh Sign-Ups (TO BUILD)

**Superseded by §8, resolved differently.** Rather than fresh accounts under
a new scheme, email was added as a second login identifier on the same 4
existing accounts — see §8. Left this section in place rather than deleting
it, since the reasoning below (why fresh accounts would have been risky) is
still the reason §8 took the approach it did.

Not yet implemented at the time this was written — noted here so it wasn't lost.

**What's wanted:** accounts should be identified by each person's personal
email address instead of a chosen username, and — rather than migrating the
existing 4 roster accounts — fresh accounts should be created for everyone
under this new scheme.

**Why this needs a decision before building:** the `roster` table's
`username` column is currently the login identifier and is `UNIQUE`; switching
to email touches login (`app.py`'s `login()` looks up by `username`), the
`add_member`/`update_member` forms, and the uniqueness constraint in
`db.py`'s schema. "Fresh accounts for everyone" also means the 190 existing
daily logs and any project ownership tied to today's 4 names need a plan for
how they map to whatever the new accounts are — that mapping is a judgment
call, not something to guess at. Flagging as pending rather than building
against assumptions.

**Where to pick this up:** `db.py`'s `roster` table schema, `app.py`'s
`login()`/`add_member()`/`update_member()` routes, `templates/team.html`'s
roster form, `templates/login.html`.

---

## 7. Upload Expanded to Cover Daily Logs Too (2026-08-18)

**What it does:** §4's upload only ever filled Projects. The original
local-folder-drop workflow was checked directly against the R&D tracking
workbook to see what else it covered — result: **only Projects**. No other
import script ever existed (this repo's entire git history is one commit;
`import_projects.py` is the only importer in it, and it only ever wrote to
`data/projects.json`). But the same workbook the Projects sheet lives in
also has a **"✅ Daily Log"** sheet, structurally matching Reportly's Daily
Logs feature exactly (Person / What Was Done / TO-DO, grouped under a date
header per day) — and the database's `reports` table turned out to already
run `2026-05-18` to `2026-08-04`, the exact same range the sheet covers,
confirming that sheet is where the original 190 report rows came from (by
hand-transcription, not a script). So the upload now covers both.

### Files involved
- `import_daily_log.py` ← new file, parses the "✅ Daily Log" sheet
- `db.py` ← new `upsert_reports()`
- `import_projects.py` ← `find_projects_sheet()` now raises `ValueError` instead of `SystemExit` (see note below)
- `app.py` ← `/projects/upload` renamed to `/upload`, now handles both datasets
- `templates/team.html` ← upload card copy updated, form action renamed

### What was done, step by step

**Investigated the sheet directly** rather than trust memory of what the old
workflow did: `RD_Project_Track_Updated.xlsx` has 11 sheets. Two map onto
real Reportly tables — **📋 Projects** (already handled) and **✅ Daily
Log** (reports). The rest don't: **📊 Dashboard** is a computed rollup of
the Projects sheet, not separate source data; **Bot Change Log** and the
five **`*- KB LOG`** sheets track AI-bot conversation/knowledge-base
history — a different system entirely, with no corresponding table in
Reportly (its own `changes` table logs changes to R&D *software projects*,
not bot conversations) — importing those would create nonsense rows, so
they're deliberately left alone.

**`import_daily_log.py` written.** Parses the day-header / person-row
pattern (a header row like ". Monday, 18 May 2026" starts a block; rows
below it are `{Person, What Was Done, TO-DO}` until a blank row). Skips
blank work entries (e.g. a holiday where only one person left a note — same
behavior the original hand-transcribed data already has). Maps the sheet's
short first names to full roster names (`Chi` → `Chiamaka`, others already
match). Accepts an optional `roster_names` set — names in the sheet that
aren't on the current roster (found: **`Ini`, `Kingsley`** — people who
apparently logged work at some point but aren't among today's 4 accounts)
are excluded from the parsed rows and returned separately as
`skipped_names`, so the caller can surface them instead of silently
dropping or misattributing their entries.

**`db.upsert_reports(rows)` added.** Reports have no ID column in the
sheet, unlike Projects (which has a real Project ID column and can use
`INSERT ... ON DUPLICATE KEY UPDATE` directly), so matching is by
**(name, date)** instead: a per-row `SELECT` to check for an existing match,
then `UPDATE` or `INSERT` accordingly — plain query-then-write rather than
`ON DUPLICATE KEY UPDATE`, since that needs a unique index to key off, and
adding one felt like more schema risk than a small number of extra queries
at this data volume. On a match,
only `raw_work`/`raw_pending` are overwritten — `status`, `generated`,
`submitted_at` etc. are left alone so a re-upload can never downgrade an
already-submitted, possibly AI-polished report back to raw sheet text. A
new (name, date) pair inserts a fresh `submitted` row.

**Bug fixed in passing:** `find_projects_sheet()` raised `SystemExit` on a
missing sheet — fine for the original CLI script (a clean-exit builtin),
wrong for a function called from inside a live web request, since
`SystemExit` isn't a subclass of `Exception` and the upload route's
`except Exception` was silently never catching it. Changed to `ValueError`
in both `import_projects.py` and the new `import_daily_log.py`; `main()`
(the CLI entry point) now catches `ValueError` and re-raises `SystemExit`
itself, so command-line behavior is unchanged.

**`/upload` route** (renamed from `/projects/upload`): reads the uploaded
workbook once, runs both parsers against it, calls `db.upsert_projects()`
and `db.upsert_reports()` for whichever produced rows, and flashes a
combined count plus any skipped names.

**Verified** via a throwaway smoke-test script (deleted after use) against
the real `RD_Project_Track_Updated.xlsx`, through Flask's test client with
an injected admin session:
- Projects: 18 matched/updated, 0 added, 0 removed (same as §4's result).
- Daily Logs: 190 → 193. The 3 new rows were `('Dami', '2026-07-16')`,
  `('Totan', '2026-07-16')`, `('Victor', '2026-07-16')` — a real gap in the
  original transcription, not a duplicate (confirmed: those exact
  (name, date) pairs didn't exist in the database beforehand).
- **Pre-existing data quirk found, not fixed:** the database separately has
  a `('Totan', '2026-07-15')` entry that isn't in the sheet at all — a
  one-day mismatch that predates this work (either the sheet's day header or
  the original hand-transcription has the wrong date for that entry). Left
  untouched rather than guessed at, since upsert never deletes unmatched
  rows either way.
- Roster and Changes counts were unaffected.
- **Idempotency check:** ran the same upload a second time — project and
  report counts stayed identical (19 / 193), confirming re-uploading the
  same sheet doesn't create duplicates.

---

## 8. Email as a Login Identifier, Added to the 4 Existing Accounts (2026-08-18)

**What it does:** Adds email as an alternative login identifier alongside
username, without creating new accounts or touching the 4 existing ones'
history. `Chiamaka`, `Totan`, `Victor`, and `Dami`'s accounts, and their
190+ daily logs and project ownership, are untouched — this only adds a new
optional column and a way to fill it in.

### Files involved
- `db.py` ← `email` column + migration, `ROSTER_COLUMNS` updated
- `app.py` ← `login()`, `add_member()`, `update_member()`
- `templates/login.html` ← label text
- `templates/team.html` ← roster edit form + add-member form

### What was done, step by step

**`db.py`:** added `email VARCHAR(255) UNIQUE` (nullable — MySQL allows
multiple `NULL`s under a `UNIQUE` index, so accounts without an email yet
don't collide with each other) to the `roster` schema, plus a
`_run_migrations()` step (`ALTER TABLE roster ADD COLUMN email ...` wrapped
in try/except, the same idempotent pattern the AppHub project's `db.py`
already uses for its own column migrations) so the change reaches the
already-existing local database, not just fresh installs. `ROSTER_COLUMNS`
updated so `save_roster()`'s whole-table replace carries the column too.

**`login()`:** now looks up the submitted identifier against
**either** `username` or `email` (case-insensitive), same password check
either way. Added a guard so an empty submitted identifier can never match
an account whose `email` is `NULL` (`(m.get("email") or "").lower()` would
otherwise turn into `""`, which — without the guard — would equal an empty
submitted username and grant a login with no real credential match).

**`add_member()` / `update_member()`:** both accept an optional `email`
field now (stored as `NULL`, not `""`, when left blank — required for the
`UNIQUE` index to behave as "no email yet" rather than colliding with every
other blank one). Both check for a case-insensitive duplicate email across
the rest of the roster before saving and flash a clear error instead of
letting the database's unique-constraint error surface raw.

**Templates:** `login.html`'s field label changed to "Username or Email"
(the `name="username"` form field itself is unchanged — still just the
submitted identifier string). `team.html`'s per-member roster row gained an
`email` input pre-filled from the account's current value, and the
add-member form gained the same field for any future roster additions.

**Verified**, via a throwaway smoke-test script (deleted after use, with
its side effects reverted immediately — see below): set an email on an
existing account, confirmed a duplicate-email attempt on a second account
was rejected with a flash message rather than crashing and left that
second account's email untouched, logged in successfully with the email,
confirmed logging in with the original username still works, and confirmed
an empty submitted identifier is rejected rather than matching an
email-less account.

**Test cleanup — done immediately, not left for later:** the smoke test set
a temporary password and a placeholder email
(`chiamaka@tgm.com`) on Chiamaka's *real* account to test the login flow
end-to-end. Both were reverted right after: her original `password_hash`
was restored from `data/roster.json` (the untouched pre-migration JSON
snapshot still on disk, which still has the real value) and her `email`
was cleared back to `NULL`. Verified via direct query afterward that all 4
accounts' `password_hash` values are back to their originals and no test
email persisted.

**Not done — deliberately:** real email addresses were not entered for any
of the 4 accounts. Setting those is a one-time admin action through the
Team Roster form whenever you're ready to hand each person their real
address to sign in with.

---

## 9. Bootstrap Admin Script + Empty-Database Bug Fix (2026-08-18)

**What it does:** Two things, found together while getting ready to deploy.
First — a way to actually log into a brand-new production database (§5's
"production starts empty" decision means there's no roster at all on day
one, and logging in requires an existing account, so nothing else in the
app can be used until *something* exists to sign in with). Second — a real
bug that would have hit that exact moment: adding the very first project,
report, change, or roster member to an empty database crashed.

### Files involved
- `seed_admin.py` ← new file, the one-time bootstrap script
- `db.py` ← `_load_table()` fixed to return a list, not a raw tuple

### What was done, step by step

**The bug:** `db.py`'s `_load_table()` returned whatever `pymysql`'s
`cursor.fetchall()` handed back directly. On a table with rows, that
happened to behave like a list everywhere it was used. On a genuinely
*empty* table, `fetchall()` returns a **tuple** — and routes throughout
`app.py` do `rows = load_x(); rows.append({...}); save_x(rows)` (adding a
project, a change, a report, a roster member all follow this exact pattern).
`tuple.append()` doesn't exist, so the very first item ever added to any
of those four tables on a fresh database would throw
`AttributeError: 'tuple' object has no attribute 'append'`. Never surfaced
before because the local dev database has had rows in every table since
the original JSON migration (§1) — nothing had queried a genuinely empty
table until this bootstrap testing did. Fixed with one word: `_load_table()`
now returns `list(cur.fetchall())`.

**`seed_admin.py` written.** A manual, run-it-yourself script — not a
boot-time feature in `app.py` (deliberately not built as one — see below).
Reads `BOOTSTRAP_ADMIN_USERNAME` (defaults to `admin`) and
`BOOTSTRAP_ADMIN_PASSWORD` (required) from the environment, refuses to run
if the roster already has anyone in it (so it can only ever seed the very
first account, never inject a second one later), and otherwise creates one
admin account with those credentials. No password is hardcoded in the
file, so it's safe to commit — the real password is supplied at run time
via the environment, once, whenever it's actually needed.

**Why a script instead of an automatic env-var-seeded boot feature** (the
pattern the AppHub project uses, where `ADMIN_EMAIL`/`ADMIN_PASSWORD` env
vars get checked and re-applied on every single boot): explicitly asked to
hold off on building that. A one-time manual script achieves the same
practical outcome — a way in on a fresh database — without adding an
always-on code path that re-asserts an account's credentials on every
deploy.

**Verified**, entirely against a throwaway `tgm_reporthub_seedtest`
database (created for this, dropped immediately after — the real local
database with the 4 real accounts was never touched):
- Ran `seed_admin.py` against the empty test database — succeeded, created
  the admin account.
- Ran it again — correctly refused, "roster already has 1 account(s)."
- Logged in through the actual `/` login route using the seeded
  credentials — worked.
- Added a first project, a first change, and a second roster member on
  that still-mostly-empty database — all three succeeded where they would
  previously have crashed, confirming the `_load_table()` fix.
- Re-ran the full 17-route smoke test from the pre-deploy check against
  the real local database afterward — no regressions from the fix.

**The actual bootstrap credentials generated this session** were shared
directly in chat, not written into any committed file — see the message
that shipped alongside this update.

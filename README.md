# TGM Report Hub

Daily reporting tool for TGM Education team.

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Create a `.env` file with:
```
SECRET_KEY=reporthub-secret-2026
OPENAI_API_KEY=your-openai-api-key-here
```

3. Run locally:
```
python app.py
```
Open http://localhost:5001

## Deploy to Railway

1. Push all files to a new GitHub repo
2. Connect to Railway → New Project → Deploy from GitHub
3. Add environment variables:
   - SECRET_KEY = reporthub-secret-2026
   - OPENAI_API_KEY = your key from platform.openai.com/api-keys
4. Generate domain in Settings → Networking

## First time setup

After deploying, the roster will be empty.
Go to the login page — you'll see no names yet.

Open the data/roster.json file and add your admin account manually,
OR go to http://yourapp.com/team after seeding the roster via the API.

Better: seed via the Procfile or a setup script (ask Claude Code to add a /setup route).

## How it works

- Team members sign in by selecting their name
- They type rough notes → click Generate → edit → Submit
- Admin sees Team tab: who's pending, all submitted reports, weekly export
- Weekly Excel export is grouped by day in roster order — paste into your existing sheet

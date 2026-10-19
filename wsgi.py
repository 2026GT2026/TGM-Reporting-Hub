"""WSGI entry point for the production server (e.g. `gunicorn wsgi:app`)."""
from app import app

# Some servers look for "application" rather than "app".
application = app

if __name__ == "__main__":
    app.run()

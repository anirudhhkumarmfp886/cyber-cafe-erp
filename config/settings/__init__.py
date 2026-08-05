"""
Settings package.

Settings are split by environment:

    config.settings.development  -> local dev (SQLite, DEBUG on)
    config.settings.production   -> production (PostgreSQL, hardened)

The default entry point ``config.settings`` (used by ``manage.py``)
loads ``.env`` and re-exports the environment selected by
``DJANGO_SETTINGS_MODULE``. When the variable is missing it falls back
to development settings so the project runs out of the box.
"""
import os

from dotenv import load_dotenv

# Load variables from the project .env file into os.environ so that
# settings modules below can read them. load_dotenv() searches the
# current working directory and parents for a .env file.
load_dotenv()

_selected = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.development")

if _selected == "config.settings.production":
    from .production import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403

"""
db.py — Shared SQLite connection factory.

Single place to adjust timeout, journal_mode, or other PRAGMAs
for all scripts and render_html.
"""

import sqlite3
from config import DB_PATH


def connect() -> sqlite3.Connection:
    """Return an open SQLite connection to the main SAINHE database."""
    con = sqlite3.connect(DB_PATH, timeout=30)
    return con

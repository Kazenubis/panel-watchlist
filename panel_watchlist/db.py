"""Tiny SQLite helper: one connection per request, schema created on startup."""

from __future__ import annotations

import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS shows (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    total_episodes   INTEGER,
    watched_episodes INTEGER NOT NULL DEFAULT 0,
    status           TEXT    NOT NULL,
    rating           INTEGER,
    notes            TEXT    NOT NULL DEFAULT '',
    updated_at       TEXT    NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open a connection that returns rows addressable by column name."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str) -> None:
    """Create the tables if they don't exist yet."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Return the connection for the current app context, opening it lazily."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    """Close the request's connection (registered as a teardown handler)."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

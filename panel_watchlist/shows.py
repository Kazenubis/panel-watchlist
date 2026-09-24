"""Show validation and data access. No Flask imports, so it's easy to unit-test."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

STATUS_LABELS: dict[str, str] = {
    "watching": "Watching",
    "completed": "Completed",
    "on-hold": "On hold",
    "dropped": "Dropped",
    "plan-to-watch": "Plan to watch",
}
STATUSES: tuple[str, ...] = tuple(STATUS_LABELS)

# Whitelisted ORDER BY clauses: user input only ever picks a key, never raw SQL.
SORTS: dict[str, tuple[str, str]] = {
    "updated": ("Recently updated", "updated_at DESC, id DESC"),
    "title": ("Title", "title COLLATE NOCASE ASC, id ASC"),
    "rating": ("Rating", "rating IS NULL, rating DESC, title COLLATE NOCASE ASC"),
}

MAX_TITLE = 120
MAX_NOTES = 1000


@dataclass
class ShowInput:
    """Cleaned form data, ready to save."""

    title: str
    total_episodes: int | None
    watched_episodes: int
    status: str
    rating: int | None
    notes: str


@dataclass
class Show:
    """A saved show as the templates see it."""

    id: int
    title: str
    total_episodes: int | None
    watched_episodes: int
    status: str
    rating: int | None
    notes: str
    updated_at: str

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def is_finished(self) -> bool:
        return self.total_episodes is not None and self.watched_episodes >= self.total_episodes

    @property
    def progress_percent(self) -> int:
        """0-100 progress; unknown totals show an empty bar."""
        if not self.total_episodes:
            return 0
        return min(100, round(100 * self.watched_episodes / self.total_episodes))


@dataclass
class Stats:
    """Numbers for the stats strip."""

    per_status: dict[str, int]
    total_shows: int
    episodes_watched: int
    average_rating: float | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _parse_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def parse_show_form(form: Mapping[str, str]) -> tuple[ShowInput | None, list[str]]:
    """Validate raw form fields. Returns (data, []) or (None, friendly_errors)."""
    errors: list[str] = []
    title = (form.get("title") or "").strip()
    raw_total = (form.get("total_episodes") or "").strip()
    raw_watched = (form.get("watched_episodes") or "").strip()
    raw_rating = (form.get("rating") or "").strip()
    status = (form.get("status") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not title:
        errors.append("Every show needs a title.")
    elif len(title) > MAX_TITLE:
        errors.append(f"Keep the title under {MAX_TITLE} characters.")

    total: int | None = None
    if raw_total:
        total = _parse_int(raw_total)
        if total is None:
            errors.append("Total episodes must be a whole number.")
        elif total < 1:
            errors.append("Total episodes must be at least 1 (leave it blank if it's still airing).")
            total = None

    watched = 0
    if raw_watched:
        parsed = _parse_int(raw_watched)
        if parsed is None:
            errors.append("Episodes watched must be a whole number.")
        elif parsed < 0:
            errors.append("Episodes watched can't be negative.")
        else:
            watched = parsed
    if total is not None and watched > total:
        errors.append("You can't have watched more episodes than the show has.")

    if status not in STATUSES:
        errors.append("Pick a status from the list.")

    rating: int | None = None
    if raw_rating:
        rating = _parse_int(raw_rating)
        if rating is None or not 1 <= rating <= 10:
            errors.append("Rating must be a whole number from 1 to 10.")

    if len(notes) > MAX_NOTES:
        errors.append(f"Notes are limited to {MAX_NOTES} characters.")

    if errors:
        return None, errors
    return ShowInput(title, total, watched, status, rating, notes), []


def _to_show(row: sqlite3.Row) -> Show:
    return Show(**{key: row[key] for key in row.keys()})


def create_show(conn: sqlite3.Connection, data: ShowInput) -> int:
    """Insert a show and return its id."""
    cur = conn.execute(
        "INSERT INTO shows (title, total_episodes, watched_episodes, status, rating, notes, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data.title, data.total_episodes, data.watched_episodes, data.status,
         data.rating, data.notes, _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_show(conn: sqlite3.Connection, show_id: int, data: ShowInput) -> None:
    conn.execute(
        "UPDATE shows SET title = ?, total_episodes = ?, watched_episodes = ?, status = ?,"
        " rating = ?, notes = ?, updated_at = ? WHERE id = ?",
        (data.title, data.total_episodes, data.watched_episodes, data.status,
         data.rating, data.notes, _now(), show_id),
    )
    conn.commit()


def delete_show(conn: sqlite3.Connection, show_id: int) -> None:
    conn.execute("DELETE FROM shows WHERE id = ?", (show_id,))
    conn.commit()


def get_show(conn: sqlite3.Connection, show_id: int) -> Show | None:
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    return _to_show(row) if row else None


def list_shows(conn: sqlite3.Connection, status: str | None = None, sort: str = "updated") -> list[Show]:
    """All shows, optionally filtered by status, in one of the SORTS orders."""
    order = SORTS.get(sort, SORTS["updated"])[1]
    if status in STATUSES:
        rows = conn.execute(f"SELECT * FROM shows WHERE status = ? ORDER BY {order}", (status,))
    else:
        rows = conn.execute(f"SELECT * FROM shows ORDER BY {order}")
    return [_to_show(row) for row in rows]


def add_episode(conn: sqlite3.Connection, show_id: int) -> str | None:
    """Watch one more episode.

    Returns "added", "completed" (just hit the final episode), "capped"
    (already at the total, nothing changed) or None if the show doesn't exist.
    """
    show = get_show(conn, show_id)
    if show is None:
        return None
    if show.is_finished:
        return "capped"
    watched = show.watched_episodes + 1
    reached_end = show.total_episodes is not None and watched >= show.total_episodes
    status = "completed" if reached_end else "watching"
    conn.execute(
        "UPDATE shows SET watched_episodes = ?, status = ?, updated_at = ? WHERE id = ?",
        (watched, status, _now(), show_id),
    )
    conn.commit()
    return "completed" if reached_end else "added"


def compute_stats(conn: sqlite3.Connection) -> Stats:
    """Counts per status, episodes watched overall, and the average rating."""
    per_status = {status: 0 for status in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM shows GROUP BY status"):
        per_status[row["status"]] = row["n"]
    totals = conn.execute(
        "SELECT COUNT(*) AS shows, COALESCE(SUM(watched_episodes), 0) AS eps, AVG(rating) AS avg"
        " FROM shows"
    ).fetchone()
    average = round(totals["avg"], 1) if totals["avg"] is not None else None
    return Stats(per_status, totals["shows"], totals["eps"], average)

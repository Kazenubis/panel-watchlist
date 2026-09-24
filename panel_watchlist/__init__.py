"""Panel Watchlist: an anime tracker that looks like a printed manga page."""

from __future__ import annotations

import os
from typing import Any

import click
from flask import Flask
from flask.cli import with_appcontext

from . import shows
from .db import close_db, get_db, init_db

SAMPLE_SHOWS: list[dict[str, Any]] = [
    {"title": "My Hero Academia", "total_episodes": None, "watched_episodes": 113,
     "status": "watching", "rating": 10, "notes": "Rewatching from season 4. Plus Ultra!"},
    {"title": "Frieren: Beyond Journey's End", "total_episodes": 28, "watched_episodes": 28,
     "status": "completed", "rating": 9, "notes": "Quiet, sad, and somehow perfect."},
    {"title": "Mob Psycho 100", "total_episodes": 37, "watched_episodes": 20,
     "status": "watching", "rating": 9, "notes": "Mob's percentage meter is the best UI in anime."},
    {"title": "Cowboy Bebop", "total_episodes": 26, "watched_episodes": 0,
     "status": "plan-to-watch", "rating": None, "notes": "Everyone says I have to. See you, space cowboy."},
    {"title": "Spy x Family", "total_episodes": 25, "watched_episodes": 11,
     "status": "on-hold", "rating": 7, "notes": ""},
    {"title": "Isekai Vending Machine Deluxe", "total_episodes": 12, "watched_episodes": 3,
     "status": "dropped", "rating": 4, "notes": "Reincarnated as a vending machine. I tapped out at episode 3."},
]


def seed_sample_shows(conn: Any) -> int:
    """Insert the sample shows that aren't there yet; returns how many were added."""
    existing = {show.title for show in shows.list_shows(conn)}
    added = 0
    for raw in reversed(SAMPLE_SHOWS):  # reversed so the first entry ends up "most recent"
        if raw["title"] in existing:
            continue
        form = {key: "" if value is None else str(value) for key, value in raw.items()}
        data, errors = shows.parse_show_form(form)
        if data is None:
            raise ValueError(f"Bad sample show {raw['title']!r}: {errors}")
        shows.create_show(conn, data)
        added += 1
    return added


@click.command("seed")
@with_appcontext
def seed_command() -> None:
    """Add a handful of sample shows to the watchlist."""
    added = seed_sample_shows(get_db())
    click.echo(f"Seeded {added} sample show(s). {len(SAMPLE_SHOWS) - added} were already there.")


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """App factory. Pass {"DATABASE": path} (and TESTING) to point at another DB."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("PANEL_WATCHLIST_SECRET", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "panel_watchlist.sqlite3"),
    )
    if config:
        app.config.update(config)

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    init_db(app.config["DATABASE"])
    app.teardown_appcontext(close_db)

    from .views import bp

    app.register_blueprint(bp)
    app.cli.add_command(seed_command)
    return app

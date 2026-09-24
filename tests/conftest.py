from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from panel_watchlist import create_app
from panel_watchlist.db import get_db
from panel_watchlist.shows import Show, get_show, list_shows


@pytest.fixture()
def app(tmp_path: Path) -> Iterator[Flask]:
    yield create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3")})


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def add_show(client: FlaskClient) -> Callable[..., Any]:
    """POST the new-show form with sensible defaults, overridable per test."""

    def _add(**fields: Any) -> Any:
        form = {"title": "Test Show", "total_episodes": "12", "watched_episodes": "0",
                "status": "watching", "rating": "", "notes": ""}
        form.update({key: str(value) for key, value in fields.items()})
        return client.post("/shows/new", data=form, follow_redirects=True)

    return _add


@pytest.fixture()
def all_shows(app: Flask) -> Callable[[], list[Show]]:
    def _all() -> list[Show]:
        with app.app_context():
            return list_shows(get_db())

    return _all


@pytest.fixture()
def fetch(app: Flask) -> Callable[[int], Show | None]:
    def _fetch(show_id: int) -> Show | None:
        with app.app_context():
            return get_show(get_db(), show_id)

    return _fetch

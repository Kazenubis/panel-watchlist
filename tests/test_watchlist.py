from __future__ import annotations

import pytest

from panel_watchlist import SAMPLE_SHOWS
from panel_watchlist.shows import parse_show_form

# ---------- create / list / edit / delete ----------


def test_create_show_appears_on_home_page(add_show, all_shows, client):
    response = add_show(title="Mob Psycho 100", total_episodes=37, watched_episodes=5, rating=9)
    assert response.status_code == 200
    assert "joined the watchlist" in response.get_data(as_text=True)

    shows = all_shows()
    assert len(shows) == 1
    assert (shows[0].title, shows[0].watched_episodes, shows[0].rating) == ("Mob Psycho 100", 5, 9)
    assert "Mob Psycho 100" in client.get("/").get_data(as_text=True)


def test_blank_total_means_still_airing(add_show, all_shows):
    add_show(title="One Piece", total_episodes="", watched_episodes=400)
    show = all_shows()[0]
    assert show.total_episodes is None
    assert show.progress_percent == 0


def test_edit_updates_every_field(add_show, all_shows, client, fetch):
    add_show(title="Old Title")
    show_id = all_shows()[0].id

    form_page = client.get(f"/shows/{show_id}/edit").get_data(as_text=True)
    assert 'value="Old Title"' in form_page

    client.post(f"/shows/{show_id}/edit", data={
        "title": "New Title", "total_episodes": "24", "watched_episodes": "3",
        "status": "on-hold", "rating": "8", "notes": "Paused for exams",
    })
    show = fetch(show_id)
    assert (show.title, show.total_episodes, show.watched_episodes) == ("New Title", 24, 3)
    assert (show.status, show.rating, show.notes) == ("on-hold", 8, "Paused for exams")


def test_delete_get_only_shows_confirmation(add_show, all_shows, client):
    add_show(title="Keep Me")
    show_id = all_shows()[0].id
    page = client.get(f"/shows/{show_id}/delete")
    assert page.status_code == 200
    assert "Delete “Keep Me”?" in page.get_data(as_text=True)
    assert len(all_shows()) == 1


def test_delete_post_removes_show(add_show, all_shows, client):
    add_show(title="Bye")
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/delete", follow_redirects=True)
    assert "removed from the watchlist" in response.get_data(as_text=True)
    assert all_shows() == []


def test_mutating_routes_reject_get(add_show, all_shows, client, fetch):
    add_show(watched_episodes=1)
    show_id = all_shows()[0].id
    assert client.get(f"/shows/{show_id}/plus-one").status_code == 405
    assert fetch(show_id).watched_episodes == 1


def test_missing_show_is_404(client):
    assert client.get("/shows/999/edit").status_code == 404
    assert client.post("/shows/999/plus-one").status_code == 404
    assert client.post("/shows/999/delete").status_code == 404


# ---------- +1 episode ----------


def test_plus_one_increments_and_starts_watching(add_show, all_shows, client, fetch):
    add_show(status="plan-to-watch", total_episodes=26, watched_episodes=0)
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/plus-one", follow_redirects=True)
    assert "Episode 1 of" in response.get_data(as_text=True)
    show = fetch(show_id)
    assert (show.watched_episodes, show.status) == (1, "watching")


def test_plus_one_auto_completes_at_total(add_show, all_shows, client, fetch):
    add_show(total_episodes=12, watched_episodes=11)
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/plus-one", follow_redirects=True)
    assert "is completed" in response.get_data(as_text=True)
    show = fetch(show_id)
    assert (show.watched_episodes, show.status) == (12, "completed")


def test_plus_one_caps_at_total(add_show, all_shows, client, fetch):
    add_show(total_episodes=12, watched_episodes=12, status="completed")
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/plus-one", follow_redirects=True)
    assert "already at its final episode" in response.get_data(as_text=True)
    assert fetch(show_id).watched_episodes == 12


def test_plus_one_without_total_keeps_counting(add_show, all_shows, client, fetch):
    add_show(total_episodes="", watched_episodes=1100)
    show_id = all_shows()[0].id
    client.post(f"/shows/{show_id}/plus-one")
    show = fetch(show_id)
    assert (show.watched_episodes, show.status) == (1101, "watching")


def test_plus_one_redirects_back_to_filtered_view(add_show, all_shows, client):
    add_show()
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/plus-one", data={"next": "/?status=watching"})
    assert response.headers["Location"] == "/?status=watching"
    evil = client.post(f"/shows/{show_id}/plus-one", data={"next": "//evil.example"})
    assert evil.headers["Location"] == "/"


# ---------- validation ----------


def test_empty_title_is_rejected(add_show, all_shows):
    response = add_show(title="   ")
    assert "Every show needs a title." in response.get_data(as_text=True)
    assert all_shows() == []


@pytest.mark.parametrize("rating", ["0", "11", "-3", "nine"])
def test_rating_out_of_range_is_rejected(add_show, all_shows, rating):
    response = add_show(rating=rating)
    assert "Rating must be a whole number from 1 to 10." in response.get_data(as_text=True)
    assert all_shows() == []


def test_negative_episodes_are_rejected(add_show, all_shows):
    html = add_show(watched_episodes=-1, total_episodes=-5).get_data(as_text=True)
    assert "Episodes watched can&#39;t be negative." in html
    assert "Total episodes must be at least 1" in html
    assert all_shows() == []


def test_parse_show_form_rules():
    base = {"title": "X", "total_episodes": "10", "watched_episodes": "", "status": "watching"}
    data, errors = parse_show_form(base)
    assert errors == [] and data.watched_episodes == 0 and data.rating is None

    _, errors = parse_show_form({**base, "watched_episodes": "11"})
    assert errors == ["You can't have watched more episodes than the show has."]
    _, errors = parse_show_form({**base, "status": "binging"})
    assert errors == ["Pick a status from the list."]


def test_invalid_edit_keeps_original_data(add_show, all_shows, client, fetch):
    add_show(title="Stable")
    show_id = all_shows()[0].id
    response = client.post(f"/shows/{show_id}/edit", data={"title": "", "status": "watching"})
    assert "Every show needs a title." in response.get_data(as_text=True)
    assert fetch(show_id).title == "Stable"


# ---------- filtering, sorting, stats ----------


def test_status_filter(add_show, client):
    add_show(title="Now Watching", status="watching")
    add_show(title="All Done", status="completed", total_episodes=12, watched_episodes=12)
    html = client.get("/?status=completed").get_data(as_text=True)
    assert "All Done" in html and "Now Watching" not in html
    # Unknown statuses fall back to showing everything.
    html = client.get("/?status=nonsense").get_data(as_text=True)
    assert "All Done" in html and "Now Watching" in html


def test_sort_by_title_and_rating(add_show, client):
    add_show(title="banana", rating=5)
    add_show(title="Apple", rating="")
    add_show(title="cherry", rating=9)
    by_title = client.get("/?sort=title").get_data(as_text=True)
    assert by_title.index("Apple") < by_title.index("banana") < by_title.index("cherry")
    by_rating = client.get("/?sort=rating").get_data(as_text=True)
    assert by_rating.index("cherry") < by_rating.index("banana") < by_rating.index("Apple")


def test_default_sort_is_recently_updated(add_show, all_shows, client):
    add_show(title="First")
    add_show(title="Second")
    first_id = next(show.id for show in all_shows() if show.title == "First")
    client.post(f"/shows/{first_id}/plus-one")
    assert [show.title for show in all_shows()] == ["First", "Second"]


def test_stats_numbers(add_show, client):
    add_show(title="A", status="watching", watched_episodes=4, rating=8)
    add_show(title="B", status="watching", watched_episodes=6, rating=7)
    add_show(title="C", status="completed", total_episodes=12, watched_episodes=12, rating=10)
    add_show(title="D", status="plan-to-watch", watched_episodes=0)
    html = client.get("/").get_data(as_text=True)
    assert 'data-stat="watching">2<' in html
    assert 'data-stat="completed">1<' in html
    assert 'data-stat="plan-to-watch">1<' in html
    assert 'data-stat="dropped">0<' in html
    assert 'data-stat="episodes">22<' in html
    assert 'data-stat="average">8.3<' in html


# ---------- seed command ----------


def test_seed_command_is_idempotent(app, all_shows):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed"])
    assert f"Seeded {len(SAMPLE_SHOWS)} sample show(s)" in first.output
    second = runner.invoke(args=["seed"])
    assert "Seeded 0 sample show(s)" in second.output
    assert len(all_shows()) == len(SAMPLE_SHOWS)

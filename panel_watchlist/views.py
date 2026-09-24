"""Routes. Every change to data is a POST; GET pages only ever read."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from . import shows
from .db import get_db

bp = Blueprint("watchlist", __name__)


def _safe_next(default: str) -> str:
    """Only follow same-site relative redirects from the hidden `next` field."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def _show_or_404(show_id: int) -> shows.Show:
    show = shows.get_show(get_db(), show_id)
    if show is None:
        abort(404)
    return show


@bp.get("/")
def index() -> str:
    status = request.args.get("status", "")
    sort = request.args.get("sort", "updated")
    if status not in shows.STATUSES:
        status = ""
    if sort not in shows.SORTS:
        sort = "updated"
    conn = get_db()
    return render_template(
        "index.html",
        shows=shows.list_shows(conn, status or None, sort),
        stats=shows.compute_stats(conn),
        current_status=status,
        current_sort=sort,
        status_labels=shows.STATUS_LABELS,
        sorts=shows.SORTS,
    )


@bp.route("/shows/new", methods=["GET", "POST"])
def new_show() -> str | Response:
    if request.method == "POST":
        data, errors = shows.parse_show_form(request.form)
        if data is not None:
            shows.create_show(get_db(), data)
            flash(f"“{data.title}” joined the watchlist!", "success")
            return redirect(url_for("watchlist.index"))
        for error in errors:
            flash(error, "error")
    return render_template("form.html", show=None, form=request.form,
                           status_labels=shows.STATUS_LABELS)


@bp.route("/shows/<int:show_id>/edit", methods=["GET", "POST"])
def edit_show(show_id: int) -> str | Response:
    show = _show_or_404(show_id)
    if request.method == "POST":
        data, errors = shows.parse_show_form(request.form)
        if data is not None:
            shows.update_show(get_db(), show_id, data)
            flash(f"Saved changes to “{data.title}”.", "success")
            return redirect(url_for("watchlist.index"))
        for error in errors:
            flash(error, "error")
        form = request.form
    else:
        form = {
            "title": show.title,
            "total_episodes": show.total_episodes if show.total_episodes is not None else "",
            "watched_episodes": show.watched_episodes,
            "status": show.status,
            "rating": show.rating if show.rating is not None else "",
            "notes": show.notes,
        }
    return render_template("form.html", show=show, form=form, status_labels=shows.STATUS_LABELS)


@bp.post("/shows/<int:show_id>/plus-one")
def plus_one(show_id: int) -> Response:
    result = shows.add_episode(get_db(), show_id)
    if result is None:
        abort(404)
    show = _show_or_404(show_id)
    messages = {
        "added": (f"Episode {show.watched_episodes} of “{show.title}” down!", "success"),
        "completed": (f"That's a wrap! “{show.title}” is completed.", "success"),
        "capped": (f"“{show.title}” is already at its final episode.", "error"),
    }
    flash(*messages[result])
    return redirect(_safe_next(url_for("watchlist.index")))


@bp.get("/shows/<int:show_id>/delete")
def confirm_delete(show_id: int) -> str:
    return render_template("confirm_delete.html", show=_show_or_404(show_id))


@bp.post("/shows/<int:show_id>/delete")
def delete_show(show_id: int) -> Response:
    show = _show_or_404(show_id)
    shows.delete_show(get_db(), show_id)
    flash(f"“{show.title}” was removed from the watchlist.", "success")
    return redirect(url_for("watchlist.index"))

"""Discord digest fixes: photo attachments, cleanup (dedupe/grouping/truncation),
and reliability (retry, partial digests, catch-up, last-sent tracking).

Run with:  pytest -q
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

TMP = Path(tempfile.mkdtemp(prefix="digest-fix-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

import app.routers.digest as digest_mod  # noqa: E402
from app import frost as frost_mod  # noqa: E402
from app.database import UPLOAD_DIR, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


# This module shares the suite's temp DB (GARDEN_DATA_DIR is set by whichever
# test module imports first), so every Album row we seed must be removed after
# the test — other tests assert exact album/photo sets.
_created_albums: list = []


@pytest.fixture(autouse=True)
def _cleanup_seeded_albums():
    yield
    while _created_albums:
        aid, fpaths = _created_albums.pop()
        with Session(engine) as s:
            album = s.get(Album, aid)
            if album is not None:
                s.delete(album)
            s.commit()
        for fp in fpaths:
            try:
                Path(fp).unlink(missing_ok=True)
            except OSError:
                pass


def _urems(*specs):
    """Fake user reminders: (title, due_date_iso, notes)."""
    return [
        SimpleNamespace(done=False, title=t, due_date=d, notes=n)
        for t, d, n in specs
    ]


def _set(**kwargs):
    with Session(engine) as s:
        for k, v in kwargs.items():
            frost_mod.set_setting(s, k, v)
        s.commit()


def _last_year_week_date():
    """A date inside this_week_last_year's window for today."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=52)
    return datetime(start.year, start.month, start.day, 12, 0, 0)


def _seed_photo(name="tt1.jpg", subdir=""):
    from PIL import Image

    init_db()
    target = UPLOAD_DIR / subdir / name if subdir else UPLOAD_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), (180, 120, 90)).save(target, "JPEG")
    with Session(engine) as s:
        album = Album(name="tt-album")
        s.add(album)
        s.commit()
        s.refresh(album)
        s.add(AlbumImage(
            album_id=album.id,
            file_path=f"/uploads/{subdir + '/' if subdir else ''}{name}",
            title=name,
            taken_at=_last_year_week_date(),
        ))
        s.commit()
        _created_albums.append((album.id, [str(target)]))
    return target


# --------------------------------------------------------------------------- #
# Problem 1 — photos attached as files, not filenames
# --------------------------------------------------------------------------- #

def test_photo_attachments_multipart(monkeypatch):
    _seed_photo("attach1.jpg")
    calls = {}

    class FakeResp:
        status_code = 204
        text = ""

    def fake_post(url, data=None, files=None, json=None, timeout=None):
        calls["data"] = data
        calls["files"] = files
        calls["json"] = json
        return FakeResp()

    monkeypatch.setattr(digest_mod.httpx, "post", fake_post)
    with Session(engine) as s:
        photos = digest_mod.collect_time_travel_photos(s)
    assert len(photos) >= 1
    name, blob, mime = photos[0]
    assert name == "attach1.jpg" and blob[:2] == b"\xff\xd8" and mime == "image/jpeg"

    digest_mod.send_discord_digest(
        "https://discord.com/api/webhooks/abc", "hello", photos, retry_delay=0)
    assert calls["json"] is None
    payload = json.loads(calls["data"]["payload_json"])
    assert payload == {"content": "hello"}
    field_name, (fname, fbytes, fmime) = calls["files"][0]
    assert field_name == "files[0]" and fname == "attach1.jpg"
    assert fbytes[:2] == b"\xff\xd8" and fmime == "image/jpeg"


def test_missing_photo_file_skipped_gracefully():
    init_db()
    with Session(engine) as s:
        album = Album(name="tt-missing")
        s.add(album)
        s.commit()
        s.refresh(album)
        s.add(AlbumImage(album_id=album.id, file_path="/uploads/nope.jpg",
                         title="gone", taken_at=_last_year_week_date()))
        s.commit()
        _created_albums.append((album.id, []))
        photos = digest_mod.collect_time_travel_photos(s)
    assert all(p[0] != "nope.jpg" for p in photos)


def test_oversized_photo_downscaled(monkeypatch):
    """A 12MB BMP over the limit comes back as a small JPEG; an
    un-downscalable giant is skipped instead of failing the send."""
    from PIL import Image

    big = UPLOAD_DIR / "big.bmp"
    try:
        Image.linear_gradient("L").resize((2000, 2000)).convert("RGB").save(big, "BMP")
        assert big.stat().st_size > 2_000_000
        monkeypatch.setattr(digest_mod, "DISCORD_FILE_LIMIT", 2_000_000)
        blob = digest_mod._read_photo_bytes(big)
        assert blob is not None
        data_bytes, mime = blob
        assert mime == "image/jpeg" and len(data_bytes) <= 2_000_000

        # Still too big after downscale -> skipped (None), never raises.
        monkeypatch.setattr(digest_mod, "DISCORD_FILE_LIMIT", 100)
        assert digest_mod._read_photo_bytes(big) is None
    finally:
        big.unlink(missing_ok=True)


def test_time_travel_block_references_attachments_not_filenames():
    with Session(engine) as s:
        block = digest_mod._time_travel_block(s, date.today(), photo_count=3)
    assert block is not None
    assert "attached below" in block
    assert ".jpg" not in block  # no bare filenames


# --------------------------------------------------------------------------- #
# Problem 2 — cleanup: truncation, dedupe, grouping, cap
# --------------------------------------------------------------------------- #

def test_truncate_never_cuts_mid_word():
    out = digest_mod._truncate("the harvest basket just keeps getting bigger", 30)
    assert "…" in out
    assert "getti" not in out and "getting" not in out
    assert out.rstrip("…").endswith("keeps")


def test_truncate_prefers_sentence_boundary():
    out = digest_mod._truncate("First frost expected Monday. Bring the peppers in tonight!", 35)
    assert out.endswith("Monday.")


def test_reminder_dedupe_collapses_case_dupes():
    rems = _urems(
        ("Plant carrots", "2026-03-05", "Early March sowing window"),
        ("plant carrots", "2026-03-05", "spring crop"),
    )
    msg = digest_mod.build_digest_message([], today=date(2026, 10, 7), user_reminders=rems)
    assert msg.lower().count("plant carrots") == 1
    # merged notes survive
    assert "spring crop" in msg


def test_reminder_fig_grouping():
    rems = _urems(
        ("Fig: prep for overwintering — stop feeding, let it harden",
         "2026-10-06", "no more fertilizer (last feed Aug 2), reduce water as it goes dormant"),
        ("Fig (17-gal bucket): move to unheated garage/shed for dormancy",
         "2026-10-19", "after first frost and once leaves drop, move into unheated space"),
        ("Move fig bucket into unheated garage/shed (once leaves dropped)",
         "2026-10-19", "Aim for 25-45F. Water sparingly, splash every 3-4 weeks"),
    )
    msg = digest_mod.build_digest_message([], today=date(2026, 10, 7), user_reminders=rems)
    # One group header, three sub-points — not three top-level fig bullets.
    assert msg.count("\n• **Fig**") == 1
    assert "prep for overwintering" in msg
    assert "move to unheated garage/shed for dormancy" in msg
    # notes truncated at a word boundary, never "wee" mid-word
    assert "3-4 wee " not in msg and "3-4 wee…" not in msg


def test_cap_drops_briefing_before_data():
    long_body = "🌱 **Morning garden check — Wed Oct 07**\n" + ("x " * 900)
    full = "🌤️ " + "briefing words " * 40 + "\n\n" + long_body + "\n\n🕰️ **This week last year**\n• 📷 2 photos"
    out = digest_mod._enforce_cap(full, has_briefing=True, has_tt=True)
    assert len(out) <= digest_mod.DISCORD_SAFE_CHARS
    assert "🌤️" not in out  # briefing dropped first
    assert "Morning garden check" in out  # header survives


# --------------------------------------------------------------------------- #
# Problem 3 — reliability: retry, partial digest, catch-up, last-sent
# --------------------------------------------------------------------------- #

def test_retry_once_on_500_then_succeeds(monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, code):
            self.status_code = code
            self.text = ""

    def fake_post(url, json=None, timeout=None, data=None, files=None):
        calls.append(url)
        return FakeResp(500 if len(calls) == 1 else 204)

    monkeypatch.setattr(digest_mod.httpx, "post", fake_post)
    digest_mod.send_discord_digest("https://discord.com/api/webhooks/abc", "hi", retry_delay=0)
    assert len(calls) == 2


def test_no_retry_on_400(monkeypatch):
    calls = []

    class FakeResp:
        status_code = 400
        text = "bad request"

    def fake_post(url, json=None, timeout=None, data=None, files=None):
        calls.append(url)
        return FakeResp()

    monkeypatch.setattr(digest_mod.httpx, "post", fake_post)
    with pytest.raises(RuntimeError):
        digest_mod.send_discord_digest("https://discord.com/api/webhooks/abc", "hi", retry_delay=0)
    assert len(calls) == 1


def test_partial_digest_when_build_fails(monkeypatch):
    monkeypatch.setattr(
        digest_mod, "build_digest_message",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with Session(engine) as s:
        result = digest_mod.build_full_digest(s, today=date(2026, 10, 7))
    assert "couldn't be built" in result.message
    assert "Morning garden check" in result.message


def test_last_sent_recorded_on_success(monkeypatch, client):
    _set(digest_enabled="true", discord_webhook_url="https://discord.com/api/webhooks/abc")
    monkeypatch.setattr(digest_mod, "send_discord_digest", lambda *a, **k: None)
    try:
        res = client.post("/api/digest/send")
        assert res.status_code == 200, res.text
        with Session(engine) as s:
            assert frost_mod.get_setting(s, "digest_last_sent") != ""
            assert frost_mod.get_setting(s, "digest_last_error") == ""
    finally:
        _set(digest_enabled="false", digest_last_sent="", digest_last_error="")


def test_last_error_recorded_on_failure(monkeypatch, client):
    _set(digest_enabled="true", discord_webhook_url="https://discord.com/api/webhooks/abc")

    def boom(*a, **k):
        raise RuntimeError("webhook exploded")

    monkeypatch.setattr(digest_mod, "send_discord_digest", boom)
    try:
        res = client.post("/api/digest/send")
        assert res.status_code == 502
        with Session(engine) as s:
            assert "webhook exploded" in frost_mod.get_setting(s, "digest_last_error")
    finally:
        _set(digest_enabled="false", digest_last_error="")


def test_preview_reports_photo_count(client):
    res = client.get("/api/digest/preview")
    assert res.status_code == 200
    assert "photos" in res.json()


def test_catchup_sends_when_today_missed(monkeypatch):
    from app import main as main_mod

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _set(digest_enabled="true",
         discord_webhook_url="https://discord.com/api/webhooks/abc",
         digest_last_sent=yesterday)
    fired = threading.Event()

    def fake_run(session, url):
        fired.set()
        return "ok"

    monkeypatch.setattr(digest_mod, "run_digest", fake_run)
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    past_hour, past_minute = (now - timedelta(minutes=5)).hour, (now - timedelta(minutes=5)).minute
    cfg = digest_mod.DigestConfig(enabled=True, webhook_url="https://x", time="08:00")
    try:
        main_mod._catch_up_missed_digest(cfg, tz, past_hour, past_minute)
        assert fired.wait(timeout=10), "catch-up digest did not fire"
    finally:
        _set(digest_enabled="false", digest_last_sent="")


def test_catchup_skips_when_already_sent_today(monkeypatch):
    from app import main as main_mod

    _set(digest_enabled="true",
         discord_webhook_url="https://discord.com/api/webhooks/abc",
         digest_last_sent=datetime.now(timezone.utc).isoformat())
    fired = threading.Event()

    def fake_run(session, url):
        fired.set()
        return "ok"

    monkeypatch.setattr(digest_mod, "run_digest", fake_run)
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    past = now - timedelta(minutes=5)
    cfg = digest_mod.DigestConfig(enabled=True, webhook_url="https://x", time="08:00")
    try:
        main_mod._catch_up_missed_digest(cfg, tz, past.hour, past.minute)
        assert not fired.wait(timeout=3), "catch-up fired despite today's send"
    finally:
        _set(digest_enabled="false", digest_last_sent="")

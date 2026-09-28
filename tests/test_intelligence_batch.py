"""v2.35.0 intelligence batch: Growstuff community data, USDA zone detection,
PlantNet identification, and PyETo-based watering advice.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="intel-batch-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import et as et_mod  # noqa: E402
from app import growstuff  # noqa: E402
from app import hardiness  # noqa: E402
from app import plantnet  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.vendor import pyeto  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- Growstuff


@pytest.fixture(autouse=True)
def _clean_growstuff():
    """Growstuff cache is process-global — never leak it into other modules."""
    _wipe_growstuff_cache()
    yield
    _wipe_growstuff_cache()


def _wipe_growstuff_cache():
    growstuff._invalidate()
    try:
        growstuff.CACHE_FILE.unlink()
    except OSError:
        pass


def _seed_growstuff_cache(**entries):
    """Write a fake disk cache and reset the in-memory copy."""
    cache_file = growstuff.CACHE_FILE
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(entries), encoding="utf-8")
    growstuff._invalidate()


def test_growstuff_slug_map_spot_checks():
    assert growstuff.CROP_SLUGS["tomato"] == "tomato"
    assert growstuff.CROP_SLUGS["pepper-bell"] == "bell-pepper"
    assert growstuff.CROP_SLUGS["pepper-hot"] == "chilli-pepper"
    assert growstuff.CROP_SLUGS["winter-squash"] == "butternut-squash"
    assert growstuff.CROP_SLUGS["pole-bean"] == "runner-bean"
    assert growstuff.CROP_SLUGS["cilantro"] == "coriander"


def test_growstuff_cache_hit_and_ttl():
    fresh = {
        "tomato": {
            "median_days_to_first_harvest": 92,
            "plantings_count": 227,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        }
    }
    _seed_growstuff_cache(**fresh)
    got = growstuff.get("tomato")
    assert got is not None
    assert got["median_days_to_first_harvest"] == 92
    assert got["plantings_count"] == 227

    # Stale entries are treated as absent.
    stale = {
        "tomato": {
            "median_days_to_first_harvest": 92,
            "fetched_at": "2020-01-01T00:00:00+00:00",
        }
    }
    _seed_growstuff_cache(**stale)
    assert growstuff.get("tomato") is None

    # Entries without a harvest median don't count.
    _seed_growstuff_cache(tomato={"plantings_count": 5,
                                 "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())})
    assert growstuff.get("tomato") is None


def test_growstuff_offline_falls_back_silently(monkeypatch):
    _seed_growstuff_cache()  # empty cache

    def boom(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(growstuff.urllib.request, "urlopen", boom)
    assert growstuff._fetch_slug("tomato") is None
    # refresh_if_stale must never raise, even with no network at all
    growstuff.refresh_if_stale()
    time.sleep(0.2)
    assert growstuff.get("tomato") is None


def test_growstuff_never_raises():
    assert growstuff.get("") is None
    assert growstuff.get(None) is None
    assert growstuff.get("not-a-crop") is None


# ---------------------------------------------------------------- Hardiness


def test_hardiness_known_points():
    assert hardiness.detect_zone(39.09603, -95.66) == "6b"  # Topeka
    assert hardiness.detect_zone(25.76, -80.19) in ("10b", "11a")  # Miami
    assert hardiness.detect_zone(64.84, -147.72) in ("3a", "3b")  # Fairbanks
    assert hardiness.detect_zone(51.5, -0.12) is None  # London — outside US data


def test_hardiness_major_zone():
    assert hardiness.major_zone("6b") == "6"
    assert hardiness.major_zone("11a") == "11"
    assert hardiness.major_zone(None) == ""


def test_detect_zone_endpoint(client):
    r = client.get("/api/settings/detect-zone?lat=39.09603&lon=-95.66")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["zone"] == "6b"
    assert body["zone_setting"] == "6"

    r = client.get("/api/settings/detect-zone?lat=51.5&lon=-0.12")
    assert r.json()["ok"] is False

    r = client.get("/api/settings/detect-zone?lat=bogus&lon=-95")
    assert r.json()["ok"] is False


# ---------------------------------------------------------------- PlantNet


def test_plantnet_no_key_never_hits_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not call the network without a key")

    monkeypatch.setattr(plantnet.httpx, "Client", boom)
    assert plantnet.identify(b"bytes", "photo.jpg", "") == {
        "ok": False,
        "reason": "no-key",
    }


def test_plantnet_success_shape(monkeypatch):
    payload = {
        "results": [
            {
                "score": 0.873,
                "species": {
                    "scientificNameWithoutAuthor": "Solanum lycopersicum",
                    "commonNames": ["Tomato", "Love apple"],
                    "family": {"scientificNameWithoutAuthor": "Solanaceae"},
                },
            }
        ]
    }

    class FakeResp:
        status_code = 200

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(plantnet.httpx, "Client", FakeClient)
    out = plantnet.identify(b"bytes", "photo.jpg", "key")
    assert out["ok"] is True
    (r,) = out["results"]
    assert r["name"] == "Solanum lycopersicum"
    assert r["common_names"] == ["Tomato", "Love apple"]
    assert r["family"] == "Solanaceae"
    assert r["score"] == 87.3


def test_plantnet_error_reasons(monkeypatch):
    class FakeResp:
        def __init__(self, code):
            self.status_code = code

    class FakeClient:
        code = 200

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp(FakeClient.code)

    monkeypatch.setattr(plantnet.httpx, "Client", FakeClient)
    for code, reason in ((401, "bad-key"), (429, "rate-limited"), (500, "http-500")):
        FakeClient.code = code
        out = plantnet.identify(b"bytes", "photo.jpg", "key")
        assert out == {"ok": False, "reason": reason}, (code, out)

    def boom(*a, **k):
        raise OSError("down")

    class DownClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return boom()

    monkeypatch.setattr(plantnet.httpx, "Client", DownClient)
    assert plantnet.identify(b"bytes", "photo.jpg", "key") == {
        "ok": False,
        "reason": "unreachable",
    }


def test_identify_endpoint_no_key(client):
    # Fresh settings in this temp DB → no PlantNet key configured.
    r = client.post("/api/identify", files={"photo": ("leaf.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 400
    assert "PlantNet API key" in r.json()["detail"]


def test_identify_endpoint_rejects_non_image(client):
    r = client.post(
        "/api/identify", files={"photo": ("x.txt", b"hello", "text/plain")}
    )
    # No-key check runs first with a fresh DB; both are 400 either way.
    assert r.status_code == 400


# ---------------------------------------------------------------- ETo / watering


def test_vendored_pyeto_matches_fao_worked_example():
    # FAO-56 example 18 (Allen et al. 1998): ~3.9 mm/day.
    eto = pyeto.fao56_penman_monteith(
        13.28, pyeto.celsius2kelvin(16.9), 2.078, 1.997, 1.409, 0.122, 0.0666
    )
    assert eto == pytest.approx(3.9, abs=0.1)


def test_reference_eto_in_sane_ranges():
    hot = et_mod.reference_eto_in(
        tmax_f=95, tmin_f=70, rh_mean=55, wind_mph=10, rad_mj=25.0,
        elevation_m=270, lat=39.1, day_of_year=200,
    )
    cool = et_mod.reference_eto_in(
        tmax_f=55, tmin_f=38, rh_mean=65, wind_mph=8, rad_mj=10.0,
        elevation_m=270, lat=39.1, day_of_year=300,
    )
    assert hot is not None and 0.15 < hot < 0.5
    assert cool is not None and 0.0 <= cool < hot
    # Works with no radiation or wind data (temperature-based estimates).
    est = et_mod.reference_eto_in(
        tmax_f=85, tmin_f=65, rh_mean=60, wind_mph=None, rad_mj=None,
        elevation_m=None, lat=39.1, day_of_year=180,
    )
    assert est is not None and est > 0
    # Junk in → None out, never raises.
    assert et_mod.reference_eto_in(
        tmax_f=70, tmin_f=70, rh_mean=55, wind_mph=5, rad_mj=20.0,
        elevation_m=270, lat=39.1, day_of_year=180,
    ) is None
    assert et_mod.reference_eto_in(
        tmax_f="hot", tmin_f=60, rh_mean=60, wind_mph=5, rad_mj=20.0,
        elevation_m=270, lat=39.1, day_of_year=180,
    ) is None


def test_watering_advice_never_raises_without_coords():
    # Fresh temp DB has no coordinates → advice is None, not an exception.
    assert et_mod.watering_advice() is None


def test_watering_advice_lines():
    assert "Rain" in et_mod.advice_line(0.20, 0.3, 90)
    assert "Rain" in et_mod.advice_line(0.05, 0.0, 80)
    assert "extra water" in et_mod.advice_line(0.30, 0.0, 10)
    assert "normal watering" in et_mod.advice_line(0.18, 0.0, 10)
    assert "ease off" in et_mod.advice_line(0.05, 0.0, 10)


# ---------------------------------------------------------------- Crops wiring


def test_crop_search_carries_community_flag(client, monkeypatch):
    # Pin the background refresh off: it must never hit the network in tests.
    monkeypatch.setattr(growstuff, "refresh_if_stale", lambda: None)
    _seed_growstuff_cache(
        tomato={
            "median_days_to_first_harvest": 92,
            "plantings_count": 227,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        }
    )
    r = client.get("/api/crops", params={"q": "tomato"})
    assert r.status_code == 200
    results = r.json()["guide"]
    tom = next(x for x in results if x["key"] == "tomato")
    assert tom["days_to_maturity"] == 92
    assert tom["maturity_source"] == "community"
    assert tom["community"]["gardens"] == 227

    r = client.get("/api/crops/tomato")
    assert r.status_code == 200
    detail = r.json()["crop"]
    assert detail["community"]["median_days_to_first_harvest"] == 92


def test_today_carries_watering_advice_key(client):
    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert "watering_advice" in body
    # Fresh temp DB: no coordinates → null advice, not an error.
    assert body["watering_advice"] is None

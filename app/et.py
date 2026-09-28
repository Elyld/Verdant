"""Reference evapotranspiration (ETo) via the vendored PyETo library.

Computes FAO-56 Penman-Monteith ETo for today from the Open-Meteo forecast
the app already fetches (temperature, humidity, wind, solar radiation),
and turns it into one gentle watering-advice line for the Today view.
Advisory only — never a lecture. Never raises: unknowable → None.
"""
from __future__ import annotations

from datetime import date as date_cls

from app.vendor import pyeto

MM_PER_INCH = 25.4


def _c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def reference_eto_in(
    *,
    tmax_f: float,
    tmin_f: float,
    rh_mean: float,
    wind_mph: float | None,
    rad_mj: float | None,
    elevation_m: float | None,
    lat: float,
    day_of_year: int,
) -> float | None:
    """FAO-56 Penman-Monteith reference ET, inches/day. None on bad input."""
    try:
        tmax, tmin = _c(float(tmax_f)), _c(float(tmin_f))
        rh = float(rh_mean)
        lat_f = float(lat)
        doy = int(day_of_year)
    except (TypeError, ValueError):
        return None
    if tmax <= tmin or not (0 <= rh <= 100):
        return None

    tmean = pyeto.daily_mean_t(tmin, tmax)
    # Wind measured at 10 m → 2 m reference height; FAO suggests 2 m/s
    # when the station reports nothing.
    ws_10 = float(wind_mph) * 0.44704 if wind_mph is not None else 2.0
    ws_2 = pyeto.wind_speed_2m(max(ws_10, 0.0), 10)

    svp = pyeto.mean_svp(tmin, tmax)
    svp_tmin = pyeto.svp_from_t(tmin)
    svp_tmax = pyeto.svp_from_t(tmax)
    avp = pyeto.avp_from_rhmean(svp_tmin, svp_tmax, rh)
    delta = pyeto.delta_svp(tmean)
    psy = pyeto.psy_const(pyeto.atm_pressure(float(elevation_m or 0.0)))

    lat_rad = pyeto.deg2rad(lat_f)
    sol_dec = pyeto.sol_dec(doy)
    sha = pyeto.sunset_hour_angle(lat_rad, sol_dec)
    et_rad = pyeto.et_rad(lat_rad, sol_dec, sha, pyeto.inv_rel_dist_earth_sun(doy))
    cs_rad = pyeto.cs_rad(float(elevation_m or 0.0), et_rad)
    if rad_mj is not None and float(rad_mj) > 0:
        sol_rad = float(rad_mj)
    else:
        sol_rad = pyeto.sol_rad_from_t(et_rad, cs_rad, tmin, tmax, coastal=False)
    net_rad = pyeto.net_rad(
        pyeto.net_in_sol_rad(sol_rad),
        # net_out_lw_rad wants absolute temperatures (Kelvin)
        pyeto.net_out_lw_rad(
            pyeto.celsius2kelvin(tmin),
            pyeto.celsius2kelvin(tmax),
            sol_rad,
            cs_rad,
            avp,
        ),
    )
    eto_mm = pyeto.fao56_penman_monteith(
        net_rad,
        pyeto.celsius2kelvin(tmean),  # this one wants Kelvin too
        ws_2,
        svp,
        avp,
        delta,
        psy,
    )
    if eto_mm is None or eto_mm < 0:
        return None
    return round(eto_mm / MM_PER_INCH, 2)


def advice_line(eto_in: float, precip_in: float, precip_prob: float) -> str:
    """One gentle watering line from today's ETo and rain outlook."""
    if precip_in >= 0.1 or precip_prob >= 70:
        return "Rain's on the way — let the sky handle the watering today. 🌧"
    if eto_in >= 0.25:
        return "Hot and thirsty out there — your plants will want extra water today. 💧"
    if eto_in >= 0.12:
        return "A warm one — a normal watering round should do it. 💧"
    return "Cool and calm — you can ease off the hose today."


def watering_advice(session=None) -> dict | None:
    """Today's ETo + one gentle watering line. None when unknowable."""
    from app import weather as weather_mod

    try:
        fc = weather_mod.get_forecast(session)
        if not fc or not fc.get("daily"):
            return None
        coords = weather_mod._coords(session)
        if coords is None:
            return None
        lat, _lon = coords
        today = fc["daily"][0]
        tmax_f, tmin_f = today.get("tmax_f"), today.get("tmin_f")
        if tmax_f is None or tmin_f is None:
            return None
        date_str = today.get("date") or ""
        rhs = [
            h.get("rh")
            for h in (fc.get("hourly") or [])
            if isinstance(h.get("rh"), (int, float))
            and str(h.get("t") or "").startswith(date_str)
        ]
        rh_mean = sum(rhs) / len(rhs) if rhs else 50.0
        current = fc.get("current") or {}
        eto_in = reference_eto_in(
            tmax_f=tmax_f,
            tmin_f=tmin_f,
            rh_mean=rh_mean,
            wind_mph=current.get("wind_mph"),
            rad_mj=today.get("rad_mj"),
            elevation_m=fc.get("elevation_m"),
            lat=lat,
            day_of_year=date_cls.today().timetuple().tm_yday,
        )
        if eto_in is None:
            return None
        precip_in = today.get("precip_in") or 0
        precip_prob = today.get("precip_prob") or 0
        line = advice_line(eto_in, precip_in, precip_prob)
        return {"eto_in": eto_in, "line": line}
    except Exception:
        return None

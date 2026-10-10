#!/usr/bin/env python3
"""Seed a believable synthetic demo garden for screenshots / README retakes.

SAFETY: refuses to run unless GARDEN_DATA_DIR is set explicitly, so it can
never touch a real garden database. Wipes all demo tables first, making
re-runs idempotent.

Usage:
    GARDEN_DATA_DIR=/tmp/verdant-demo GARDEN_UPLOAD_DIR=/tmp/verdant-demo/uploads \\
        python scripts/seed_demo.py

All dates are relative to "today" so screenshots stay fresh whenever retaken.
All photos are PIL-generated placeholders (solid sage blocks + labels) —
never real user photos.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = os.getenv("GARDEN_DATA_DIR")
if not DATA_DIR:
    sys.exit("REFUSING: set GARDEN_DATA_DIR to a scratch dir (never a real garden).")
DATA_DIR = Path(DATA_DIR)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["GARDEN_DATA_DIR"] = str(DATA_DIR)

from PIL import Image, ImageDraw  # noqa: E402

from app.database import UPLOAD_DIR, init_db  # noqa: E402
from sqlmodel import Session, SQLModel, delete, select  # noqa: E402

from app import models as m  # noqa: E402

TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731


# --------------------------------------------------------------------------- #
# placeholder images
# --------------------------------------------------------------------------- #
def placeholder(label: str, sub: str = "", hue=(122, 139, 111), size=(640, 480)) -> Image.Image:
    """A simple garden-y placeholder: solid block + label text."""
    im = Image.new("RGB", size, hue)
    d = ImageDraw.Draw(im)
    # subtle border
    d.rectangle([8, 8, size[0] - 8, size[1] - 8], outline=(255, 255, 255), width=3)
    # label (PIL default font; centered-ish)
    d.text((24, size[1] // 2 - 20), label, fill=(255, 255, 255))
    if sub:
        d.text((24, size[1] // 2 + 8), sub, fill=(240, 240, 230))
    return im


def save_placeholder(rel: str, label: str, sub: str = "", hue=(122, 139, 111)) -> str:
    """Write a placeholder PNG under UPLOAD_DIR; return its /uploads URL path."""
    target = UPLOAD_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    placeholder(label, sub, hue).save(target)
    return "/uploads/" + rel


# --------------------------------------------------------------------------- #
# wipe
# --------------------------------------------------------------------------- #
TABLES = [
    m.AgentDraft, m.AgentMessage, m.AgentConversation, m.AgentFile,
    m.ObservationImage, m.ObservationLog, m.WateringLog, m.FertilizationLog,
    m.Harvest, m.PreservationLog, m.PantryItem, m.PestLog,
    m.InvoiceSeedPacket, m.ExpenseSeedPacket, m.Invoice, m.Expense,
    m.SeedlingBatch, m.SeedPacket, m.WishlistItem, m.SeedSource,
    m.AlbumImage, m.Album, m.PostImage, m.Post,
    m.Planting, m.Container, m.Plant, m.Location,
    m.Fertilizer, m.GardenTag, m.UserReminder, m.BookCheck,
]


def wipe(session: Session) -> None:
    for model in TABLES:
        session.exec(delete(model))
    # settings: keep the table, reset demo keys below
    session.commit()


def main() -> None:
    init_db()
    from app.database import engine

    with Session(engine) as s:
        wipe(s)

        # ---------------- locations ----------------
        bed1 = m.Location(name="Raised Bed 1", type="Raised bed", light="Full Sun")
        bags = m.Location(name="Grow bags", type="Container", light="Full Sun")
        patio = m.Location(name="Back patio pots", type="Container", light="Part Shade")
        s.add_all([bed1, bags, patio])
        s.flush()

        # ---------------- plants ----------------
        plants = {}
        defs = [
            ("Cherokee Purple", "Tomato", "Solanum lycopersicum", "Vegetable", bed1.id, 2, 14, 75),
            ("Sungold", "Tomato", "Solanum lycopersicum", "Vegetable", bed1.id, 2, 14, 65),
            ("Habanero", "Pepper", "Capsicum chinense", "Vegetable", bags.id, 3, 21, 90),
            ("California Wonder", "Pepper", "Capsicum annuum", "Vegetable", bags.id, 3, 21, 75),
            ("Genovese Basil", "Herb", "Ocimum basilicum", "Herb", patio.id, 2, None, 68),
            ("Marketmore Cucumber", "Cucumber", "Cucumis sativus", "Vegetable", bed1.id, 2, 14, 60),
            ("State Fair Zinnia", "Flower", "Zinnia elegans", "Flower", patio.id, 4, None, 70),
            ("Music Garlic", "Garlic", "Allium sativum", "Vegetable", bed1.id, 7, None, 240),
        ]
        for name, species, sci, cat, loc_id, water, feed, dtm in defs:
            p = m.Plant(
                variety_name=name, species_type=species, family_genus=sci,
                category=cat, status="Growing", location_id=loc_id,
                date_planted=TODAY - timedelta(days=90),
                days_to_maturity=dtm, water_every_days=water, feed_every_days=feed,
                notes=f"Demo plant: {name}.",
            )
            s.add(p)
            s.flush()
            plants[name] = p

        # ---------------- observations ----------------
        obs_notes = [
            ("Cherokee Purple", 1, 8, True, "", "First blush on two fruits — picking tomorrow."),
            ("Cherokee Purple", 4, 9, True, "", "Loaded with green fruit after the rain."),
            ("Sungold", 2, 9, True, "", "Cracking on a few — picked the ripe cluster."),
            ("Habanero", 3, 7, True, "aphids on new growth", "Sprayed neem; will recheck in 3 days."),
            ("Genovese Basil", 2, 8, True, "", "Pinched flower heads; bushy regrowth."),
            ("Marketmore Cucumber", 5, 6, False, "", "Wilted at noon, perked up by evening — heat, not water."),
            ("California Wonder", 6, 8, True, "", "First peppers sizing up nicely."),
            ("State Fair Zinnia", 3, 9, True, "", "Butterflies all over the blooms."),
        ]
        for name, days_ago, health, watered, pests, notes in obs_notes:
            s.add(m.ObservationLog(
                date=D(days_ago), plant_name=name, plant_id=plants[name].id,
                health_scale=health, watering_status=watered,
                pest_sightings=pests or None, notes=notes,
                temp_c=24.5, weather_summary="Sunny",
            ))
        s.flush()

        # ---------------- watering / fertilizing ----------------
        # Cherokee Purple watered 1 day ago (due today-ish); Habanero 3 days ago (due today)
        s.add(m.WateringLog(plant_id=plants["Cherokee Purple"].id, date=D(1), method="drip"))
        s.add(m.WateringLog(plant_id=plants["Sungold"].id, date=D(1), method="drip"))
        s.add(m.WateringLog(plant_id=plants["Habanero"].id, date=D(3), method="can"))
        s.add(m.WateringLog(plant_id=plants["Genovese Basil"].id, date=D(2), method="can"))
        fert1 = m.Fertilizer(fertilizer_id="FERT-DEMO-1", name="Tomato-tone",
                             npk_ratio="3-4-6", best_for="Tomatoes & peppers")
        fert2 = m.Fertilizer(fertilizer_id="FERT-DEMO-2", name="Fish emulsion",
                             npk_ratio="5-1-1", best_for="Leafy greens & herbs")
        fert3 = m.Fertilizer(fertilizer_id="FERT-DEMO-3", name="All-purpose 10-10-10",
                             npk_ratio="10-10-10", best_for="Everything")
        s.add_all([fert1, fert2, fert3])
        s.flush()
        s.add(m.FertilizationLog(date=D(13), fertilizer_name="Tomato-tone",
                                 fertilizer_id=fert1.id, plant_id=plants["Cherokee Purple"].id,
                                 amount_used="2 tbsp / gal"))
        s.add(m.FertilizationLog(date=D(6), fertilizer_name="Fish emulsion",
                                 fertilizer_id=fert2.id, plant_id=plants["Genovese Basil"].id,
                                 amount_used="1 tbsp / gal"))
        s.flush()

        # ---------------- harvests ----------------
        for name, days_ago, qty, wt in [
            ("Cherokee Purple", 1, 6, 32.0), ("Cherokee Purple", 8, 8, 40.0),
            ("Sungold", 2, 24, 12.0), ("Habanero", 4, 14, 6.0),
            ("Genovese Basil", 3, 4, 3.0), ("Marketmore Cucumber", 5, 3, 18.0),
        ]:
            s.add(m.Harvest(plant_id=plants[name].id, date=D(days_ago),
                            quantity=qty, unit="fruit", weight=wt, weight_unit="oz",
                            notes="Demo harvest"))
        s.flush()

        # ---------------- seed sources / packets / wishlist ----------------
        src1 = m.SeedSource(source_id="SRC-DEMO-1", source="Baker Creek",
                            variety="", type="Vendor Purchase")
        src2 = m.SeedSource(source_id="SRC-DEMO-2", source="Territorial Seed",
                            variety="", type="Vendor Purchase")
        src3 = m.SeedSource(source_id="SRC-DEMO-3", source="Johnny's Selected Seeds",
                            variety="", type="Vendor Purchase")
        s.add_all([src1, src2, src3])
        s.flush()

        packets = {}
        pdefs = [
            ("Cherokee Purple", "Tomato", "Baker Creek", 2026, "~40 seeds", 40, "favorite"),
            ("Genovese Basil", "Herb", "Territorial Seed", 2025, "~200 seeds", 200, "yes"),
            ("Habanero", "Pepper", "Baker Creek", 2026, "~25 seeds", 25, "yes"),
            ("Marketmore Cucumber", "Cucumber", "Baker Creek", 2026, "~30 seeds", 30, ""),
            ("Sungold", "Tomato", "Johnny's Selected Seeds", 2026, "~25 seeds", 25, "favorite"),
            ("California Wonder", "Pepper", "Baker Creek", 2026, "~30 seeds", 30, ""),
            ("State Fair Zinnia", "Flower", "Territorial Seed", 2025, "~50 seeds", 50, "no"),
        ]
        for i, (name, cat, vendor, year, qty, count, again) in enumerate(pdefs):
            p = m.SeedPacket(
                variety_name=name, category=cat, vendor_name=vendor,
                year_acquired=year, quantity=qty, seed_count=count,
                grow_again=again, date_added=D(60),
                photo_path=f"/uploads/seed-packets/demo-{i}/front.png",
                photo_back_path=f"/uploads/seed-packets/demo-{i}/back.png",
                notes="Demo packet",
            )
            s.add(p)
            s.flush()
            packets[name] = p
            save_placeholder(f"seed-packets/demo-{i}/front.png", name, f"{vendor} · {year}")
            save_placeholder(f"seed-packets/demo-{i}/back.png", f"{name} — back",
                             "Sow after frost · full sun", hue=(96, 110, 88))

        for v, vendor, notes in [
            ("Jimmy Nardello", "Baker Creek", "Sweet frying pepper — try next year"),
            ("Dragon Tongue", "Territorial Seed", "Bush bean, no trellis needed"),
        ]:
            s.add(m.WishlistItem(variety_name=v, vendor_name=vendor, notes=notes,
                                 checked=True, date_added=D(20)))
        s.flush()

        # ---------------- seedling batches ----------------
        for name, days_ago, tray, cells, germ, status in [
            ("Cherokee Purple", 95, "Tray A", 12, 11, "transplanted"),
            ("Habanero", 100, "Tray A", 12, 9, "transplanted"),
            ("Genovese Basil", 80, "Tray B", 24, 22, "transplanted"),
        ]:
            s.add(m.SeedlingBatch(
                variety_name=name, sow_date=D(days_ago), tray=tray,
                location="basement shelf", heat_mat=True,
                grow_light="LED shop light, 16h/day",
                cells_sown=cells, germinated=germ,
                germination_date=D(days_ago - 10), status=status,
                transplant_date=D(days_ago - 60),
                notes="Demo batch",
            ))
        s.flush()

        # ---------------- expenses + invoices (books-badge GREEN) ----------------
        # Every invoice links to a same-total expense: no warnings, no errors.
        exp_defs = [
            ("2026-01-22", "Seeds", "Baker Creek seed order", 41.75),
            ("2026-02-02", "Seeds", "Territorial Seed order", 24.95),
            ("2026-03-05", "Supplies", "Row cover clips and plant labels", 17.60),
            ("2026-04-20", "Supplies", "Grow bags (5-pack)", 24.99),
            ("2026-05-01", "Soil", "Raised bed soil mix", 68.00),
            ("2026-05-01", "Fertilizer", "Tomato-tone + fish emulsion", 31.75),
        ]
        expenses = {}
        for dt, cat, desc, amt in exp_defs:
            e = m.Expense(date=dt, category=cat, description=desc, amount=amt)
            s.add(e)
            s.flush()
            expenses[desc] = e

        inv_defs = [
            # vendor, order_date, order_number, total, items_summary, email_link, source, expense
            ("Baker Creek", "2026-01-22", "BC-2026-0109", 41.75,
             "Cherokee Purple tomato, Habanero pepper, Marketmore cucumber seeds",
             "https://mail.google.com/mail/u/0/#all/18c4a2b9d4e6f012", "gmail",
             "Baker Creek seed order"),
            ("Territorial Seed", "2026-02-02", "TS-2026-8841", 24.95,
             "Genovese Basil and Sungold tomato seeds",
             "https://mail.google.com/mail/u/0/#all/18c4a2b9d4e6f013", "gmail",
             "Territorial Seed order"),
            ("Johnny's Selected Seeds", "2026-03-05", "JS-552031", 17.60,
             "Row cover clips and plant labels",
             None, "manual", "Row cover clips and plant labels"),
        ]
        for vendor, odt, onum, total, items, elink, src, exp_desc in inv_defs:
            inv = m.Invoice(
                vendor=vendor, order_date=odt, order_number=onum, total=total,
                items_summary=items, email_link=elink, source=src,
                expense_id=expenses[exp_desc].id,
            )
            s.add(inv)
            s.flush()
            # link the seed-type invoices to their packets (like derive-packets would)
            if "Baker Creek" in vendor:
                for pn in ("Cherokee Purple", "Habanero", "Marketmore Cucumber"):
                    s.add(m.InvoiceSeedPacket(invoice_id=inv.id,
                                              seed_packet_id=packets[pn].id))
            if "Territorial" in vendor:
                for pn in ("Genovese Basil", "Sungold"):
                    s.add(m.InvoiceSeedPacket(invoice_id=inv.id,
                                              seed_packet_id=packets[pn].id))
        s.flush()

        # ---------------- planner: containers + plantings ----------------
        cont_defs = [
            ("Raised Bed 1", "raised bed", "4x8 ft", 0, 0, 4, 2),
            ("Grow Bag 1", "grow bag", "10 gal", 5, 0, 1, 1),
            ("Grow Bag 2", "grow bag", "10 gal", 6, 0, 1, 1),
            ("Patio Pot 1", "pot", "5 gal", 0, 3, 1, 1),
            ("Cold Frame", "cold frame", "3x3 ft", 2, 3, 2, 2),  # empty: succession ideas
        ]
        for name, kind, size, gx, gy, gw, gh in cont_defs:
            s.add(m.Container(name=name, kind=kind, size=size, season_year=TODAY.year,
                              grid_x=gx, grid_y=gy, grid_w=gw, grid_h=gh))
        s.flush()
        conts = {c.name: c for c in s.exec(select(m.Container)).all()}
        for cname, pname in [
            ("Raised Bed 1", "Cherokee Purple"), ("Raised Bed 1", "Sungold"),
            ("Raised Bed 1", "Marketmore Cucumber"), ("Grow Bag 1", "Habanero"),
            ("Grow Bag 2", "California Wonder"), ("Patio Pot 1", "Genovese Basil"),
        ]:
            s.add(m.Planting(container_id=conts[cname].id, plant_id=plants[pname].id,
                             season_year=TODAY.year))
        s.flush()

        # ---------------- albums / photos ----------------
        album = m.Album(name="2026 Garden", source_url="")
        s.add(album)
        s.flush()
        hues = [(122, 139, 111), (100, 130, 120), (140, 125, 95), (110, 120, 140)]
        for i, (label, sub) in enumerate([
            ("Cherokee Purple", "first ripe fruit"), ("Sungold", "cluster on the vine"),
            ("Habanero", "sizing up"), ("Raised Bed 1", "mid-July overview"),
            ("Genovese Basil", "after pinching"), ("Zinnias", "butterflies"),
            ("Harvest basket", "Saturday haul"), ("Seedlings", "tray A under lights"),
        ]):
            rel = f"albums/demo/{i}.png"
            url = save_placeholder(rel, label, sub, hue=hues[i % 4])
            plant_id = plants.get(label.split()[0] + (" Purple" if "Cherokee" in label else ""), None)
            plant_id = plant_id.id if plant_id else None
            # assign a few to plants; leave others unassigned for /match
            if i in (0, 1, 2):
                nm = ["Cherokee Purple", "Sungold", "Habanero"][i]
                plant_id = plants[nm].id
            else:
                plant_id = None
            s.add(m.AlbumImage(album_id=album.id, file_path=url, title=label,
                               taken_at=None, plant_id=plant_id))
        s.flush()

        # observation photos (2 on the latest Cherokee Purple log)
        obs = s.exec(select(m.ObservationLog).where(
            m.ObservationLog.plant_name == "Cherokee Purple"
        ).order_by(m.ObservationLog.date.desc())).first()
        if obs:
            for i in range(2):
                url = save_placeholder(f"observations/demo/{i}.png",
                                       "Cherokee Purple", "observation photo")
                s.add(m.ObservationImage(observation_id=obs.id, file_path=url))
        s.flush()

        # ---------------- blog ----------------
        for title, content in [
            ("First Sungolds of the year",
             "## Sweet as candy\n\nPicked the first ripe Sungold cluster today. "
             "The kids ate half of them standing right there in the garden."),
            ("What the habaneros taught me",
             "## Patience\n\nPeppers are slow. Start them early, keep them warm, "
             "and don't panic when the tomatoes lap them twice over."),
        ]:
            s.add(m.Post(title=title, content=content))
        s.flush()

        # ---------------- pests ----------------
        s.add(m.PestLog(date=D(3), pest_name="Aphids",
                        plant_id=plants["Habanero"].id,
                        treatment="Neem oil spray", resolved=False,
                        notes="Clustered on new growth; recheck in 3 days."))
        s.add(m.PestLog(date=D(30), pest_name="Tomato hornworm",
                        plant_id=plants["Cherokee Purple"].id,
                        treatment="Hand-picked", resolved=True,
                        notes="Two big ones, relocated to the far fence."))
        s.flush()

        # ---------------- pantry ----------------
        s.add(m.PreservationLog(date=D(10), method="canned",
                                variety_name="Cherokee Purple",
                                plant_id=plants["Cherokee Purple"].id,
                                qty_in=12, qty_in_unit="lbs", qty_out=7,
                                qty_out_unit="quarts", stored_location="pantry shelf",
                                notes="Demo batch"))
        s.add(m.PreservationLog(date=D(6), method="frozen",
                                variety_name="Habanero",
                                plant_id=plants["Habanero"].id,
                                qty_in=2, qty_in_unit="lbs", qty_out=2,
                                qty_out_unit="bags", stored_location="freezer",
                                notes="Whole, for winter salsa"))
        for name, method, qty, unit, loc in [
            ("Canned Cherokee Purple tomatoes", "canned", 5, "quarts", "pantry shelf"),
            ("Frozen habaneros", "frozen", 2, "bags", "freezer"),
            ("Dried basil", "dehydrated", 3, "jars", "pantry shelf"),
        ]:
            s.add(m.PantryItem(name=name, method=method, quantity=qty, unit=unit,
                               stored_date=D(10), location=loc))
        s.flush()

        # ---------------- tags ----------------
        for label, action, target in [
            ("Neem oil bottle", "pest", "neem oil"),
            ("Tomato-tone bag", "fertilize", "Tomato-tone"),
            ("Harvest basket", "harvest", ""),
        ]:
            s.add(m.GardenTag(label=label, action=action, target_text=target,
                              tap_count=4))
        s.flush()

        # ---------------- agent ----------------
        conv = m.AgentConversation(title="Tomato check-in")
        s.add(conv)
        s.flush()
        s.add(m.AgentMessage(conversation_id=conv.id, role="user",
                             content="how are the tomatoes doing?"))
        s.add(m.AgentMessage(conversation_id=conv.id, role="assistant",
                             content="Looking great — the Cherokee Purple was watered "
                             "yesterday and the basil could use a feeding. I've drafted "
                             "both below."))
        import json
        s.add(m.AgentDraft(conversation_id=conv.id, kind="water",
                           payload_json=json.dumps({"plant": "Cherokee Purple",
                                                    "note": "morning watering"})))
        s.add(m.AgentDraft(conversation_id=conv.id, kind="memory_write",
                           payload_json=json.dumps(
                               {"text": "Prefers Cherokee Purple over Better Boy for flavor"})))
        for name, content in [
            ("soul.md", "You are Verdant, the assistant inside a gardener's personal garden journal.\n"),
            ("AGENTS.md", "# Operating notes — lessons you learn about this garden.\n"),
            ("MEMORY.md", "# Memory — durable facts.\n- Garden is in Topeka, KS (zone 6b)\n"),
        ]:
            s.add(m.AgentFile(name=name, content=content))
        s.flush()

        # ---------------- reminders ----------------
        s.add(m.UserReminder(title="Start garlic in the raised bed",
                             due_date=(TODAY + timedelta(days=6)).isoformat(),
                             notes="Demo reminder"))
        s.flush()

        # ---------------- settings ----------------
        demo_settings = {
            "garden_lat": "39.0489",
            "garden_lon": "-95.6780",
            "zone": "6b",
            "ai_provider": "ollama",
        }
        for k, v in demo_settings.items():
            s.add(m.Setting(key=k, value=v))
        s.commit()

    print(f"demo garden seeded into {DATA_DIR} (uploads: {UPLOAD_DIR})")


if __name__ == "__main__":
    main()

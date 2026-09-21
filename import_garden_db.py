import csv
import os
from datetime import datetime
from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import (
    Location,
    Plant,
    Fertilizer,
    SeedSource,
    FertilizationLog,
    Harvest,
    WateringLog,
)

CSV_DIR = "."  # Directory containing the export CSV files


def parse_csv(path):
    """Parse a CSV file and return a list of dictionaries."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_date(date_str):
    """Parse date string in MM/DD/YYYY format."""
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_date_or_datetime(date_str):
    """Parse date or datetime string."""
    if not date_str:
        return None

    try:
        # Try datetime first
        dt = datetime.strptime(
            date_str.strip(), "%m/%d/%Y %I:%M:%S %p"
        )
        return dt
    except ValueError:
        pass

    try:
        # Try date only
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def import_locations(session):
    """Import locations from CSV."""
    print("Importing locations...")
    path = os.path.join(CSV_DIR, "export - Locations.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return {}

    rows = parse_csv(path)
    location_map = {}

    for row in rows:
        loc_id_str = row.get("Location ID", "").strip()
        loc_name = row.get("Name", "").strip()

        if not loc_id_str or not loc_name:
            continue

        # Check if already exists
        existing = session.exec(
            select(Location).where(Location.location_id == loc_id_str)
        ).first()

        if existing:
            location_map[loc_id_str] = existing.id
            continue

        location = Location(
            location_id=loc_id_str,
            name=loc_name,
            type=row.get("Type", "Container").strip(),
            light=row.get("Light", "Full Sun").strip(),
            pot_size=row.get("Pot Size", "").strip() or None,
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(location)
        session.flush()
        location_map[loc_id_str] = location.id
        print(f"  {loc_id_str}: {loc_name}")

    session.commit()
    print(f"  Imported {len(location_map)} locations")
    return location_map


def import_plants(session, location_map):
    """Import plants from CSV."""
    print("Importing plants...")
    path = os.path.join(CSV_DIR, "export - Plants.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return {}

    rows = parse_csv(path)
    plant_map = {}

    for row in rows:
        plant_id_str = row.get("Plant ID", "").strip()
        variety_name = row.get("Variety Name", "").strip()

        if not plant_id_str or not variety_name:
            continue

        # Check if already exists
        existing = session.exec(
            select(Plant).where(Plant.plant_id == plant_id_str)
        ).first()

        if existing:
            plant_map[plant_id_str] = existing.id
            continue

        loc_id_str = row.get("Location", "").strip()
        loc_id = location_map.get(loc_id_str)

        plant = Plant(
            plant_id=plant_id_str,
            variety_name=variety_name,
            species_type=row.get("Species / Type", "").strip(),
            family_genus=row.get("Family / Genus", "").strip() or None,
            category=row.get("Category", "Annual").strip(),
            status=row.get("Status", "Growing").strip(),
            location_id=loc_id,
            date_started_indoors=parse_date(
                row.get("Date Started Indoors", "")
            ),
            date_planted=parse_date(row.get("Date Planted", "")),
            light=row.get("Light", "Full Sun").strip(),
            pot_size=row.get("Notes", "").strip() or None,
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(plant)
        session.flush()
        plant_map[plant_id_str] = plant.id
        print(f"  {plant_id_str}: {variety_name}")

    session.commit()
    print(f"  Imported {len(plant_map)} plants")
    return plant_map


def import_fertilizers(session):
    """Import fertilizers from CSV."""
    print("Importing fertilizers...")
    path = os.path.join(CSV_DIR, "export - Fertilizers.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return {}

    rows = parse_csv(path)
    fert_map = {}

    for row in rows:
        fert_id_str = row.get("Fertilizer ID", "").strip()
        name = row.get("Name", "").strip()

        if not fert_id_str or not name:
            continue

        existing = session.exec(
            select(Fertilizer).where(
                Fertilizer.fertilizer_id == fert_id_str
            )
        ).first()

        if existing:
            fert_map[fert_id_str] = existing.id
            continue

        fertilizer = Fertilizer(
            fertilizer_id=fert_id_str,
            name=name,
            npk_ratio=row.get("N-P-K", "").strip() or None,
            best_for=row.get("Best For", "").strip() or None,
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(fertilizer)
        session.flush()
        fert_map[fert_id_str] = fertilizer.id
        print(f"  {fert_id_str}: {name}")

    session.commit()
    print(f"  Imported {len(fert_map)} fertilizers")
    return fert_map


def import_seed_sources(session, plant_map):
    """Import seed sources from CSV."""
    print("Importing seed sources...")
    path = os.path.join(CSV_DIR, "export - Seed Sources.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return

    rows = parse_csv(path)

    for row in rows:
        source_id_str = row.get("Source ID", "").strip()
        source = row.get("Source", "").strip()
        variety = row.get("Variety", "").strip()

        if not source_id_str or not source:
            continue

        existing = session.exec(
            select(SeedSource).where(
                SeedSource.source_id == source_id_str
            )
        ).first()

        if existing:
            continue

        seed_source = SeedSource(
            source_id=source_id_str,
            source=source,
            variety=variety,
            type=row.get("Type", "Vendor Purchase").strip(),
            acquired_date=parse_date(row.get("Acquired Date", "")),
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(seed_source)

    session.commit()
    print("  Imported seed sources")


def import_fertilization_logs(session, plant_map, location_map, fert_map):
    """Import fertilization logs from CSV."""
    print("Importing fertilization logs...")
    path = os.path.join(CSV_DIR, "export - Fertilization Logs.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return

    rows = parse_csv(path)
    count = 0

    for row in rows:
        fert_id_str = row.get("Fertilization ID", "").strip()
        date_str = row.get("Date", "").strip()
        fertilizer_name = row.get("Fertilizer", "").strip()

        if not fert_id_str or not date_str:
            continue

        log_date = parse_date(date_str)
        if not log_date:
            continue

        # Try to match fertilizer by name
        fert_id = None
        for fid, name in fert_map.items():
            if (
                name.lower() in fertilizer_name.lower()
                or fertilizer_name.lower() in name.lower()
            ):
                fert_id = fid
                break

        # Try to match plant by name
        plant_id = None
        plant_name = row.get("Plant", "").strip()

        for pid, name in plant_map.items():
            if name.lower() == plant_name.lower():
                plant_id = pid
                break

        log = FertilizationLog(
            date=log_date,
            fertilizer_name=fertilizer_name,
            fertilizer_id=fert_id,
            npk_ratio=row.get("N-P-K", "").strip() or None,
            amount_used=row.get("Amount", "").strip() or None,
            plant_id=plant_id,
            location_id=None,  # Will be added later
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(log)
        count += 1

    session.commit()
    print(f"  Imported {count} fertilization logs")


def import_watering_logs(session, location_map):
    """Import watering logs from CSV."""
    print("Importing watering logs...")
    path = os.path.join(CSV_DIR, "export - Watering Logs.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return

    rows = parse_csv(path)
    count = 0

    for row in rows:
        watering_id_str = row.get("Watering ID", "").strip()
        date_str = row.get("Date", "").strip()
        location_name = row.get("Location", "").strip()

        if not watering_id_str or not date_str:
            continue

        log_date = parse_date(date_str)
        if not log_date:
            continue

        # Try to match location by name
        loc_id = None
        for loc_id_str, loc_name in location_map.items():
            if loc_name.lower() == location_name.lower():
                loc_id = loc_id_str
                break

        if not loc_id:
            continue

        log = WateringLog(
            watering_id=watering_id_str,
            location_id=loc_id,
            date=log_date,
            method=row.get("Method", "").strip() or None,
            amount=row.get("Amount", "").strip() or None,
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(log)
        count += 1

    session.commit()
    print(f"  Imported {count} watering logs")


def import_harvest_logs(session, plant_map):
    """Import harvest logs from CSV."""
    print("Importing harvest logs...")
    path = os.path.join(CSV_DIR, "export - Harvest Logs.csv")

    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return

    rows = parse_csv(path)
    count = 0

    for row in rows:
        harvest_id_str = row.get("Harvest ID", "").strip()
        date_str = row.get("Date", "").strip()
        plant_name = row.get("Plant", "").strip()
        quantity_str = row.get("Quantity", "").strip()

        if not harvest_id_str or not date_str:
            continue

        harvest_date = parse_date(date_str)
        if not harvest_date:
            continue

        # Try to match plant by name
        plant_id = None
        for pid, name in plant_map.items():
            if name.lower() == plant_name.lower():
                plant_id = pid
                break

        if not plant_id:
            continue

        try:
            quantity = int(quantity_str) if quantity_str else 0
        except ValueError:
            quantity = 0

        harvest = Harvest(
            harvest_id=harvest_id_str,
            plant_id=plant_id,
            date=harvest_date,
            quantity=quantity,
            unit=row.get("Unit", "fruit").strip() or "fruit",
            weight=(
                float(row.get("Weight", ""))
                if row.get("Weight", "").strip()
                else None
            ),
            notes=row.get("Notes", "").strip() or None,
        )

        session.add(harvest)
        count += 1

    session.commit()
    print(f"  Imported {count} harvest logs")


def main():
    print("Verdant v2.0 - Garden Database Import Script")
    print("=" * 50)

    # Initialize database
    init_db()

    # Import in correct order
    with Session(engine) as session:
        location_map = import_locations(session)
        plant_map = import_plants(session, location_map)
        fert_map = import_fertilizers(session)
        import_seed_sources(session, plant_map)
        import_fertilization_logs(
            session, plant_map, location_map, fert_map
        )
        import_watering_logs(session, location_map)
        import_harvest_logs(session, plant_map)

    print("=" * 50)
    print("Import complete!")
    print("Database: data/garden.db")


if __name__ == "__main__":
    main()
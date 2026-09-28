"""Build the compact USDA hardiness-zone lookup used by app/hardiness.py.

Source data (both MIT / public):
  - Zone per ZIP: PRISM Climate Group 2023 Plant Hardiness Zone dataset,
    https://prism.oregonstate.edu/phzm/  (phzm_us/ak/hi/pr_zipcode_2023.csv)
  - ZIP centroids: waldoj/frostline (https://github.com/waldoj/frostline),
    MIT licensed, file zipcodes.csv.

Usage:
    python3 build_zip_zones.py /path/to/prism_csvs /path/to/frostline_zipcodes.csv

Writes:
    zip_zones.bin       -- packed (lat_cdeg int16, lon_cdeg int16, zone_idx uint8)
    zip_zones_meta.json -- zone label table + provenance

The runtime reader (app/hardiness.py) does a nearest-centroid lookup; no
GIS dependency needed at runtime.
"""
from __future__ import annotations

import csv
import json
import struct
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
MAGIC = b"VZZ1"


def main() -> None:
    prism_dir = Path(sys.argv[1])
    frostline_csv = Path(sys.argv[2])

    zones: dict[str, str] = {}
    for csv_file in sorted(prism_dir.glob("phzm_*_zipcode_2023.csv")):
        with open(csv_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                zones[row["zipcode"].strip()] = row["zone"].strip()

    coords: dict[str, tuple[float, float]] = {}
    with open(frostline_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                coords[row["zipcode"].strip()] = (
                    float(row["latitude"]),
                    float(row["longitude"]),
                )
            except (ValueError, KeyError):
                continue

    joined = [
        (coords[z][0], coords[z][1], zones[z]) for z in zones if z in coords
    ]
    labels = sorted({z for _, _, z in joined})
    label_idx = {label: i for i, label in enumerate(labels)}

    blob = bytearray(MAGIC)
    blob += struct.pack(">I", len(joined))
    for lat, lon, zone in joined:
        blob += struct.pack(
            ">hhB", round(lat * 100), round(lon * 100), label_idx[zone]
        )

    (OUT_DIR / "zip_zones.bin").write_bytes(bytes(blob))
    (OUT_DIR / "zip_zones_meta.json").write_text(
        json.dumps(
            {
                "labels": labels,
                "records": len(joined),
                "vintage": "2023",
                "sources": [
                    "PRISM Climate Group, Oregon State University (phzm 2023)",
                    "waldoj/frostline zipcodes.csv (MIT)",
                ],
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(joined)} records, {len(labels)} zone labels")


if __name__ == "__main__":
    main()

"""Rebuild migrations/data/countries.csv: GDELT's FIPS country codes -> ISO codes, names, regions.

GDELT places events with FIPS 10-4 country codes. GeoNames maps FIPS to ISO, and the
World Bank assigns ISO countries to its 7 regions. Territories the World Bank doesn't
classify are assigned by hand below.

Run once from backend/: `uv run python scripts/build_countries.py`
"""

import csv
from pathlib import Path

import httpx

GEONAMES_URL = "https://download.geonames.org/export/dump/countryInfo.txt"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"
OUT = Path(__file__).resolve().parent.parent / "migrations" / "data" / "countries.csv"

# World Bank region for territories it doesn't list, keyed by ISO alpha-3. None = no region.
MANUAL_REGIONS = {
    "ATA": None,
    "BVT": None,
    "HMD": None,
    "SGS": None,
    "ATF": None,  # Antarctic
    "AIA": "LCN",
    "BLM": "LCN",
    "GLP": "LCN",
    "MTQ": "LCN",
    "MSR": "LCN",
    "ANT": "LCN",
    "FLK": "LCN",
    "GUF": "LCN",
    "SPM": "NAC",
    "CCK": "EAS",
    "COK": "EAS",
    "CXR": "EAS",
    "NFK": "EAS",
    "NIU": "EAS",
    "PCN": "EAS",
    "TKL": "EAS",
    "TWN": "EAS",
    "WLF": "EAS",
    "IOT": "SAS",
    "GGY": "ECS",
    "JEY": "ECS",
    "SJM": "ECS",
    "VAT": "ECS",
    "SCG": "ECS",
    "ESH": "MEA",
    "REU": "SSF",
    "SHN": "SSF",
    "MYT": "SSF",
}

# FIPS splits the Palestinian territories into West Bank (WE) and Gaza Strip (GZ).
NAME_OVERRIDES = {"WE": "West Bank"}

# FIPS codes GDELT uses that GeoNames has no row for: (fips, iso2, iso3, name, region).
EXTRA = [
    ("GZ", "PS", "PSE", "Gaza Strip", "MEA"),
    ("PF", "", "", "Paracel Islands", "EAS"),
    ("PG", "", "", "Spratly Islands", "EAS"),
]


def main() -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        geonames = client.get(GEONAMES_URL).text
        world_bank = client.get(WORLD_BANK_URL).json()[1]

    wb_region = {c["id"]: c["region"]["id"] for c in world_bank if c["region"]["id"] != "NA"}
    rows = []
    for line in geonames.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = line.split("\t")
        iso2, iso3, fips, name = fields[0], fields[1], fields[3], fields[4].strip()
        if not fips:
            continue
        region = wb_region[iso3] if iso3 in wb_region else MANUAL_REGIONS[iso3]
        rows.append((fips, iso2, iso3, NAME_OVERRIDES.get(fips, name), region or ""))
    rows.extend(EXTRA)
    rows.sort()

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["fips_code", "iso2", "iso3", "name", "region_id"])
        writer.writerows(rows)
    print(f"wrote {len(rows)} countries to {OUT}")


if __name__ == "__main__":
    main()

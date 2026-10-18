"""Turn one GDELT export row into an event to store, or reject it."""

from dataclasses import dataclass
from datetime import date, datetime

from flashpoint.gdelt import parse_timestamp

CONFLICT_ROOT_CODES = range(14, 21)  # CAMEO 14 (protest) to 20 (mass violence)
EXPORT_COLUMNS = 61

# Column positions in a GDELT 2.0 export row (0-based).
GLOBALEVENTID = 0
SQLDATE = 1
ACTOR1_NAME = 6
ACTOR1_COUNTRY = 7
ACTOR2_NAME = 16
ACTOR2_COUNTRY = 17
EVENT_CODE = 26
EVENT_ROOT_CODE = 28
GOLDSTEIN = 30
NUM_MENTIONS = 31
NUM_SOURCES = 32
NUM_ARTICLES = 33
AVG_TONE = 34
ACTION_GEO_TYPE = 51
ACTION_GEO_FULLNAME = 52
ACTION_GEO_COUNTRY = 53
ACTION_GEO_LAT = 56
ACTION_GEO_LONG = 57
DATEADDED = 59
SOURCEURL = 60


@dataclass(frozen=True)
class Event:
    global_event_id: int
    date_added: datetime
    event_date: date
    root_code: int
    event_code: str
    goldstein: float | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None
    avg_tone: float | None
    actor1_name: str | None
    actor1_country: str | None
    actor2_name: str | None
    actor2_country: str | None
    geo_type: int
    place_name: str | None
    country_code: str | None
    lat: float
    lon: float
    source_url: str | None


def _text(value: str) -> str | None:
    return value.strip() or None


def _int(value: str) -> int | None:
    return int(value) if value.strip() else None


def _float(value: str) -> float | None:
    return float(value) if value.strip() else None


def parse_row(row: list[str]) -> Event | None:
    """The event in this row, or None if it isn't a mappable conflict event."""
    if len(row) != EXPORT_COLUMNS:
        return None
    try:
        root_code = int(row[EVENT_ROOT_CODE])
        if root_code not in CONFLICT_ROOT_CODES:
            return None
        geo_type = _int(row[ACTION_GEO_TYPE])
        lat, lon = _float(row[ACTION_GEO_LAT]), _float(row[ACTION_GEO_LONG])
        if not geo_type or lat is None or lon is None:
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return Event(
            global_event_id=int(row[GLOBALEVENTID]),
            date_added=parse_timestamp(row[DATEADDED]),
            event_date=datetime.strptime(row[SQLDATE], "%Y%m%d").date(),
            root_code=root_code,
            event_code=row[EVENT_CODE].strip(),
            goldstein=_float(row[GOLDSTEIN]),
            num_mentions=_int(row[NUM_MENTIONS]),
            num_sources=_int(row[NUM_SOURCES]),
            num_articles=_int(row[NUM_ARTICLES]),
            avg_tone=_float(row[AVG_TONE]),
            actor1_name=_text(row[ACTOR1_NAME]),
            actor1_country=_text(row[ACTOR1_COUNTRY]),
            actor2_name=_text(row[ACTOR2_NAME]),
            actor2_country=_text(row[ACTOR2_COUNTRY]),
            geo_type=geo_type,
            place_name=_text(row[ACTION_GEO_FULLNAME]),
            country_code=_text(row[ACTION_GEO_COUNTRY]),
            lat=lat,
            lon=lon,
            source_url=_text(row[SOURCEURL]),
        )
    except ValueError:
        return None

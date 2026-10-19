"""Build synthetic GDELT export files and serve them from a fake GDELT server.

Tests describe events with a few keyword arguments; everything else gets a realistic default.
"""

import io
import itertools
import zipfile
from datetime import UTC, datetime

import httpx

from flashpoint.gdelt import BASE_URL, GdeltSource, format_timestamp

_ids = itertools.count(1_000_000_000)


def gdelt_row(
    *,
    event_id: int | None = None,
    root_code: int = 19,
    event_code: str | None = None,
    lat: float | str = 15.5,
    lon: float | str = 32.5,
    geo_type: int | str = 4,
    country: str = "SU",
    place: str = "Khartoum, Khartoum, Sudan",
    added: datetime = datetime(2026, 10, 18, 9, 15, tzinfo=UTC),
    event_date: str | None = None,
    articles: int = 6,
    sources: int = 2,
    url: str = "https://example.com/news/article",
) -> list[str]:
    """One 61-column GDELT 2.0 export row."""
    row = [""] * 61
    row[0] = str(event_id if event_id is not None else next(_ids))
    row[1] = event_date or added.strftime("%Y%m%d")
    row[2], row[3] = added.strftime("%Y%m"), added.strftime("%Y")
    row[4] = "2026.7863"
    row[5], row[6], row[7] = "SDNMIL", "SUDAN", "SDN"
    row[15], row[16], row[17] = "SDNREB", "RAPID SUPPORT FORCES", "SDN"
    row[25] = "1"
    row[26] = event_code or f"{root_code}0"
    row[27] = row[26]
    row[28] = str(root_code)
    row[29] = "4"
    row[30], row[31], row[32], row[33], row[34] = "-10.0", "6", str(sources), str(articles), "-8.5"
    row[51], row[52], row[53] = str(geo_type), place, country
    row[56], row[57] = str(lat), str(lon)
    row[59] = format_timestamp(added)
    row[60] = url
    return row


def export_zip(rows: list[list[str]], ts: datetime) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        body = "\n".join("\t".join(row) for row in rows) + "\n"
        archive.writestr(f"{format_timestamp(ts)}.export.CSV", body)
    return buffer.getvalue()


class FakeGdelt:
    """Serves lastupdate.txt and export files for the timestamps a test has published."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.broken: set[str] = set()
        self.latest: datetime | None = None

    def publish(self, ts: datetime, rows: list[list[str]]) -> None:
        self.files[format_timestamp(ts)] = export_zip(rows, ts)
        if self.latest is None or ts > self.latest:
            self.latest = ts

    def handler(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "lastupdate.txt":
            stamp = format_timestamp(self.latest)
            listing = (
                f"1000 abc {BASE_URL}/{stamp}.export.CSV.zip\n"
                f"1000 abc {BASE_URL}/{stamp}.mentions.CSV.zip\n"
            )
            return httpx.Response(200, text=listing)
        stamp = name.split(".")[0]
        if stamp in self.broken:
            return httpx.Response(500)
        if stamp in self.files:
            return httpx.Response(200, content=self.files[stamp])
        return httpx.Response(404)

    def source(self) -> GdeltSource:
        return GdeltSource(httpx.Client(transport=httpx.MockTransport(self.handler)))

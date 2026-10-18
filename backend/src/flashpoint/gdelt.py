"""The only code that talks to GDELT: find the newest 15-minute export and download exports.

GDELT 2.0 publishes one zipped, tab-separated "export" file of events every 15 minutes,
named by its UTC timestamp, e.g. 20261018091500.export.CSV.zip.
"""

import csv
import io
import zipfile
from datetime import UTC, datetime

import httpx

BASE_URL = "https://data.gdeltproject.org/gdeltv2"
TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"


def format_timestamp(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


class GdeltSource:
    def __init__(self, client: httpx.Client, base_url: str = BASE_URL) -> None:
        self.client = client
        self.base_url = base_url

    def latest_timestamp(self) -> datetime:
        """Timestamp of the newest export, from lastupdate.txt ("<size> <md5> <url>" per line)."""
        response = self.client.get(f"{self.base_url}/lastupdate.txt")
        response.raise_for_status()
        for line in response.text.splitlines():
            url = line.split()[-1]
            if url.endswith(".export.CSV.zip"):
                return parse_timestamp(url.rsplit("/", 1)[-1].split(".")[0])
        raise ValueError("lastupdate.txt lists no export file")

    def fetch_export(self, ts: datetime) -> list[list[str]] | None:
        """All rows of one export file, or None if GDELT has no file for that timestamp."""
        response = self.client.get(f"{self.base_url}/{format_timestamp(ts)}.export.CSV.zip")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            raw = archive.read(archive.namelist()[0])
        # QUOTE_NONE: GDELT doesn't quote fields, and names can contain stray quote marks.
        text = raw.decode("utf-8", errors="replace")
        return list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))

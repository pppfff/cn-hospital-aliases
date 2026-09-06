"""Import NMPA trial participation exports with strict provenance validation.

The public web search currently returns an access challenge in this environment.
This adapter handles legitimately obtained UTF-8 exports and saved detail pages;
it does not automate challenge solving or pretend filings are trial records.
"""

from __future__ import annotations

import csv
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

FIELDS = ("trial_id", "facility_name", "province_reported", "city_reported", "source_url", "accessed_at")
HEADERS = {"登记号": "trial_id", "机构名称": "facility_name", "医院名称": "facility_name", "省份": "province_reported", "城市": "city_reported", "来源网址": "source_url", "采集日期": "accessed_at"}


def validate_participation(row: dict[str, str]) -> dict[str, str]:
    from datetime import date
    record = {field: str(row.get(field) or "").strip() for field in FIELDS}
    if not re.fullmatch(r"CTR\d{8}", record["trial_id"]):
        raise ValueError("NMPA trial_id must be CTR followed by eight digits")
    if not record["facility_name"]:
        raise ValueError("NMPA participation needs an explicitly reported institution name")
    source = urlparse(record["source_url"])
    if source.scheme not in {"http", "https"} or source.hostname not in {"chinadrugtrials.org.cn", "www.chinadrugtrials.org.cn"}:
        raise ValueError("NMPA source_url must identify the official trial detail page")
    if "searchlistdetail" not in source.path:
        raise ValueError("NMPA source_url must be a trial detail page, not a listing")
    url_ids = parse_qs(source.query).get("reg_no", [])
    if url_ids and url_ids != [record["trial_id"]]:
        raise ValueError("NMPA URL registration ID disagrees with the exported row")
    date.fromisoformat(record["accessed_at"])
    return {"source_registry": "NMPA_CDE", **record}


def read_participation_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("NMPA export has no header")
        columns = {HEADERS.get(field, field) for field in reader.fieldnames}
        if not {"trial_id", "facility_name", "source_url", "accessed_at"} <= columns:
            raise ValueError("NMPA export requires trial_id, facility_name, source_url and accessed_at")
        rows = [validate_participation({HEADERS.get(key, key): value for key, value in row.items()}) for row in reader]
    unique = {tuple(row[field] for field in ("trial_id", "facility_name", "province_reported", "city_reported")): row for row in rows}
    return sorted(unique.values(), key=lambda row: (row["trial_id"], row["facility_name"]))


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            if self.row is not None:
                self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None


def parse_detail_html(html: str, *, source_url: str, accessed_at: str) -> list[dict[str, str]]:
    parser = _TableParser()
    parser.feed(html)
    text = " ".join(parser.text)
    ids = set(re.findall(r"\bCTR\d{8}\b", text))
    if len(ids) != 1:
        raise ValueError("Saved detail page must contain exactly one CTR registration ID")
    header = None
    output = []
    for row in parser.rows:
        if "机构名称" in row and ("国家" in row or "省（州）" in row or "城市" in row):
            header = row
            continue
        if header is None or len(row) != len(header):
            continue
        values = dict(zip(header, row))
        country = values.get("国家", "")
        if country not in {"中国", "中国大陆", "China"}:
            continue
        output.append(validate_participation({
            "trial_id": next(iter(ids)), "facility_name": values.get("机构名称", ""),
            "province_reported": values.get("省（州）", values.get("省份", "")),
            "city_reported": values.get("城市", ""), "source_url": source_url,
            "accessed_at": accessed_at,
        }))
    if not output:
        raise ValueError("No explicit China participating-institution table found; do not treat as an empty trial")
    return output

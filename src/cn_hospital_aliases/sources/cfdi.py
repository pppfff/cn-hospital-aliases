"""Read the public CFDI drug-trial institution listing, never gated details."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PUBLIC_URL = "https://beian.cfdi.org.cn/CTMDS/apps/pub/drugPublic1.jsp"
LIST_URL = "https://beian.cfdi.org.cn/CTMDS/pub/PUB010100.do"
FIELDS = ("companyId", "compName", "areaName", "address", "recordNo", "recordStatus")


def fetch_institutions(output_dir: Path, *, delay: float = 15.0) -> dict:
    """Cache public pages in supported batches; stop on access challenges.

    Contact names and telephone numbers are deliberately not retained. A
    filing establishes registration, not participation in any particular trial.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("complete"):
            return previous
    page_number, expected_total = 1, None
    institutions = {}
    hashes = {}
    while True:
        path = output_dir / f"page-{page_number:05d}.json"
        params = {"method": "handle06", "curPage": page_number, "pageSize": 100}
        url = LIST_URL + "?" + urlencode(params)
        if path.exists():
            page = json.loads(path.read_text(encoding="utf-8"))
        else:
            request = Request(url, headers={"User-Agent": "cn-hospital-aliases/0.3 (public institution research)"})
            with urlopen(request, timeout=40) as response:
                if response.status != 200:
                    raise RuntimeError(f"CFDI access stopped: HTTP {response.status}")
                raw = response.read()
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError("CFDI did not return public list JSON; access stopped") from exc
            if not payload.get("success") or not isinstance(payload.get("data"), list):
                raise RuntimeError("CFDI public list schema changed or access denied")
            page = {
                "totalRows": int(payload["totalRows"]),
                "curPage": int(payload["curPage"]),
                "page_size": 100,
                "source_url": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "data": [{key: row.get(key, "") for key in FIELDS} for row in payload["data"]],
            }
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(page, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(path)
            time.sleep(max(delay, 15.0))
        if page.get("page_size") != 100:
            raise RuntimeError("Use a new snapshot directory when page size changes")
        if page["curPage"] != page_number:
            raise RuntimeError("CFDI returned an unexpected page; refusing repeated results")
        expected_total = expected_total or page["totalRows"]
        if page["totalRows"] != expected_total:
            raise RuntimeError("CFDI total changed during collection; use a new snapshot directory")
        for row in page["data"]:
            key = row["companyId"]
            if not key or key in institutions:
                raise RuntimeError(f"CFDI empty or duplicate companyId on page {page_number}")
            institutions[key] = row
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if page_number == 1 or page_number % 20 == 0:
            print(f"CFDI page {page_number}: {len(institutions)}/{expected_total} institutions", flush=True)
        if len(institutions) == expected_total:
            break
        if not page["data"] or len(institutions) > expected_total:
            raise RuntimeError("CFDI pagination did not reconcile to the declared total")
        page_number += 1
    manifest = {
        "complete": True, "source": "CFDI public drug-trial institution filings",
        "source_url": PUBLIC_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "total_institutions": len(institutions), "page_count": page_number,
        "retained_fields": list(FIELDS), "file_sha256": hashes,
        "participation_evidence": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def read_institutions(output_dir: Path) -> list[dict]:
    """Require a complete, checksum-verified list snapshot."""
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise ValueError("CFDI snapshot is incomplete")
    rows = []
    for filename, expected in manifest["file_sha256"].items():
        path = output_dir / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"CFDI checksum mismatch: {filename}")
        page = json.loads(path.read_text(encoding="utf-8"))
        rows.extend({**row, "source_url": page["source_url"], "accessed_at": page["retrieved_at"][:10]} for row in page["data"])
    if len(rows) != manifest["total_institutions"]:
        raise ValueError("CFDI row count mismatch")
    return rows

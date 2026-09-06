"""ClinicalTrials.gov China interventional-site ingestion pipeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from difflib import SequenceMatcher
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..normalizer import normalize_name
from ..registry import HospitalRegistry


API_BASE = "https://clinicaltrials.gov/api/v2/studies"
VERSION_URL = "https://clinicaltrials.gov/api/v2/version"
QUERY_LOCATION = "AREA[LocationCountry]China"
QUERY_TERM = "AREA[StudyType]INTERVENTIONAL"
FIELDS = (
    "NCTId,StudyType,LocationFacility,LocationCity,LocationState,"
    "LocationCountry,LocationStatus,LastUpdatePostDate"
)
ACTIVE_STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
}

_HOSPITAL_RE = re.compile(
    r"医院|医療院|妇幼保健院|婦幼保健院|hospital|medical\s+cent(?:er|re)|"
    r"cancer\s+cent(?:er|re)|infirmary",
    re.IGNORECASE,
)
_CLINIC_RE = re.compile(r"诊所|診所|门诊部|門診部|clinic|polyclinic", re.IGNORECASE)
_NON_SPECIFIC_RE = re.compile(
    r"^(local (institution|site)|research site|investigative site|study site|"
    r"site(\s*(number|no\.?|#)?\s*[:\-]?\s*[a-z0-9]+)?|not available|n/?a)$",
    re.IGNORECASE,
)
_HAN_RE = re.compile(r"[\u3400-\u9fff]")


def fetch_all_study_pages(
    output_dir: Path,
    *,
    refresh: bool = False,
    max_pages: int | None = None,
    timeout: int = 60,
    max_retries: int = 5,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Download all paginated China interventional-study records.

    Page files are atomic and resumable. A completed manifest makes a repeated
    call a no-op unless ``refresh`` is true.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists() and not refresh:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("complete"):
            progress(f"using completed snapshot: {manifest_path}")
            return manifest

    if refresh:
        for path in output_dir.glob("page-*.json"):
            path.unlink()
        for path in (manifest_path, output_dir / "checkpoint.json"):
            if path.exists():
                path.unlink()

    existing = sorted(output_dir.glob("page-*.json"))
    next_page_token: str | None = None
    page_number = 1
    total_count: int | None = None
    if existing:
        last_path = existing[-1]
        page_number = int(last_path.stem.split("-")[-1]) + 1
        last_page = json.loads(last_path.read_text(encoding="utf-8"))
        next_page_token = last_page.get("nextPageToken")
        checkpoint_path = output_dir / "checkpoint.json"
        if checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            total_count = checkpoint.get("total_count")
        if not next_page_token:
            progress("last cached page has no next token; finalizing snapshot")

    api_version = _fetch_json(VERSION_URL, timeout=timeout, max_retries=max_retries)
    while not existing or next_page_token:
        if max_pages is not None and page_number > max_pages:
            break
        params = {
            "query.locn": QUERY_LOCATION,
            "query.term": QUERY_TERM,
            "format": "json",
            "pageSize": "1000",
            "countTotal": "true" if page_number == 1 else "false",
            "fields": FIELDS,
        }
        if next_page_token:
            params["pageToken"] = next_page_token
        url = f"{API_BASE}?{urlencode(params)}"
        page = _fetch_json(url, timeout=timeout, max_retries=max_retries)
        if page_number == 1:
            total_count = page.get("totalCount")
        page_path = output_dir / f"page-{page_number:05d}.json"
        _atomic_json_write(page_path, page)
        existing.append(page_path)
        next_page_token = page.get("nextPageToken")
        checkpoint = {
            "complete": False,
            "page_count": page_number,
            "total_count": total_count,
            "next_page_token": next_page_token,
        }
        _atomic_json_write(output_dir / "checkpoint.json", checkpoint)
        progress(
            f"downloaded page {page_number}: {len(page.get('studies', []))} studies"
        )
        page_number += 1
        if not next_page_token:
            break

    complete = next_page_token is None
    manifest = {
        "complete": complete,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source": "ClinicalTrials.gov API v2",
        "source_url": API_BASE,
        "api_version": api_version,
        "query_location": QUERY_LOCATION,
        "query_term": QUERY_TERM,
        "fields": FIELDS.split(","),
        "total_study_count": total_count,
        "page_count": len(existing),
    }
    _atomic_json_write(manifest_path, manifest)
    return manifest


def extract_mentions(page_paths: Iterable[Path]) -> list[dict[str, str]]:
    """Extract China facility facts from downloaded API pages."""

    unique: dict[tuple[str, ...], dict[str, str]] = {}
    for page_path in page_paths:
        page = json.loads(page_path.read_text(encoding="utf-8"))
        for study in page.get("studies", []):
            protocol = study.get("protocolSection", {})
            nct_id = protocol.get("identificationModule", {}).get("nctId", "")
            study_type = protocol.get("designModule", {}).get("studyType", "")
            last_update = (
                protocol.get("statusModule", {})
                .get("lastUpdatePostDateStruct", {})
                .get("date", "")
            )
            locations = protocol.get("contactsLocationsModule", {}).get("locations", [])
            for location in locations:
                if location.get("country") != "China":
                    continue
                facility = _clean(location.get("facility", ""))
                if not facility:
                    continue
                row = {
                    "source_registry": "ClinicalTrials.gov",
                    "trial_id": nct_id,
                    "study_type": study_type,
                    "trial_last_update": last_update,
                    "facility_name": facility,
                    "city_reported": _clean(location.get("city", "")),
                    "province_reported": _clean(location.get("state", "")),
                    "country": "China",
                    "site_status": _clean(location.get("status", "")),
                    "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
                }
                key = tuple(row.values())
                unique[key] = row
    return sorted(
        unique.values(),
        key=lambda row: (
            row["province_reported"],
            row["city_reported"],
            normalize_name(row["facility_name"]),
            row["trial_id"],
        ),
    )


def aggregate_sites(mentions: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Aggregate punctuation/case variants without asserting broader aliases."""

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in mentions:
        key = (
            normalize_name(row["facility_name"]),
            normalize_name(row["province_reported"]),
            normalize_name(row["city_reported"]),
        )
        group = groups.setdefault(
            key,
            {
                "variants": Counter(),
                "trial_ids": set(),
                "active_trial_ids": set(),
                "latest_trial_update": "",
                "province_reported": row["province_reported"],
                "city_reported": row["city_reported"],
            },
        )
        group["variants"][row["facility_name"]] += 1
        group["trial_ids"].add(row["trial_id"])
        if row["site_status"] in ACTIVE_STATUSES:
            group["active_trial_ids"].add(row["trial_id"])
        group["latest_trial_update"] = max(
            group["latest_trial_update"], row["trial_last_update"]
        )

    sites: list[dict[str, Any]] = []
    for key, group in groups.items():
        variants = sorted(
            group["variants"],
            key=lambda name: (-group["variants"][name], -len(name), name),
        )
        canonical = variants[0]
        trial_ids = sorted(group["trial_ids"])
        digest_input = "\x1f".join(key).encode("utf-8")
        site_id = "ctg-" + hashlib.sha256(digest_input).hexdigest()[:16]
        sites.append(
            {
                "site_id": site_id,
                "canonical_reported_name": canonical,
                "province_reported": group["province_reported"],
                "city_reported": group["city_reported"],
                "country": "China",
                "facility_type_guess": classify_facility(canonical),
                "verification_status": "registry_reported",
                "trial_count": len(trial_ids),
                "active_trial_count": len(group["active_trial_ids"]),
                "name_variant_count": len(variants),
                "name_variants": " | ".join(variants),
                "first_trial_id": trial_ids[0],
                "latest_trial_update": group["latest_trial_update"],
                "source_registry": "ClinicalTrials.gov",
                "source_url": f"https://clinicaltrials.gov/study/{trial_ids[0]}",
            }
        )
    return sorted(
        sites,
        key=lambda row: (
            row["province_reported"],
            row["city_reported"],
            normalize_name(row["canonical_reported_name"]),
        ),
    )


def classify_facility(name: str) -> str:
    normalized = " ".join(name.split())
    if _NON_SPECIFIC_RE.fullmatch(normalized):
        return "non_specific"
    if _HOSPITAL_RE.search(normalized):
        return "hospital"
    if _CLINIC_RE.search(normalized):
        return "clinic"
    return "other_facility"


def generate_alias_candidates(
    hospital_sites: Iterable[dict[str, Any]], *, min_score: float = 0.9
) -> list[dict[str, str]]:
    """Create high-similarity, same-location pairs for manual review only."""

    blocks: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for site in hospital_sites:
        name = site["canonical_reported_name"]
        script = "han" if _HAN_RE.search(name) else "latin"
        block = (
            normalize_name(site["province_reported"]),
            normalize_name(site["city_reported"]),
            script,
        )
        blocks[block].append(site)

    output: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for block_sites in blocks.values():
        trigram_index: dict[str, set[int]] = defaultdict(set)
        normalized_names = [normalize_name(site["canonical_reported_name"]) for site in block_sites]
        for right_index, right_name in enumerate(normalized_names):
            candidates: set[int] = set()
            grams = _ngrams(right_name)
            for gram in grams:
                candidates.update(trigram_index.get(gram, set()))
            for left_index in candidates:
                left_name = normalized_names[left_index]
                if not left_name or not right_name or left_name == right_name:
                    continue
                length_ratio = min(len(left_name), len(right_name)) / max(
                    len(left_name), len(right_name)
                )
                if length_ratio < 0.7:
                    continue
                score = SequenceMatcher(None, left_name, right_name).ratio()
                if score < min_score:
                    continue
                left = block_sites[left_index]
                right = block_sites[right_index]
                pair = tuple(sorted((left["site_id"], right["site_id"])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                output.append(
                    {
                        "left_site_id": left["site_id"],
                        "left_name": left["canonical_reported_name"],
                        "right_site_id": right["site_id"],
                        "right_name": right["canonical_reported_name"],
                        "province_reported": right["province_reported"],
                        "city_reported": right["city_reported"],
                        "similarity": f"{score:.6f}",
                        "decision": "manual_review",
                    }
                )
            for gram in grams:
                trigram_index[gram].add(right_index)
    return sorted(output, key=lambda row: (-float(row["similarity"]), row["left_name"], row["right_name"]))


def write_snapshot(
    mentions: list[dict[str, str]],
    sites: list[dict[str, Any]],
    *,
    processed_dir: Path,
    review_dir: Path,
    package_output: Path,
    verified_registry: HospitalRegistry,
    accessed_at: str,
    total_study_count: int | None = None,
    source_data_timestamp: str | None = None,
) -> dict[str, Any]:
    """Write deterministic compressed tables and package registry records."""

    processed_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    package_output.parent.mkdir(parents=True, exist_ok=True)
    hospitals = [site for site in sites if site["facility_type_guess"] == "hospital"]
    alias_candidates = generate_alias_candidates(hospitals)
    verified_keys = _verified_location_keys(verified_registry)
    verified_matches: list[dict[str, Any]] = []
    unverified_hospitals: list[dict[str, Any]] = []
    for site in hospitals:
        key = (
            normalize_name(site["canonical_reported_name"]),
            normalize_name(site["province_reported"]),
            normalize_name(site["city_reported"]),
        )
        verified_id = verified_keys.get(key)
        if verified_id:
            verified_matches.append({**site, "verified_hospital_id": verified_id})
        else:
            unverified_hospitals.append(site)

    write_csv_gz(processed_dir / "facility_mentions.csv.gz", mentions)
    write_csv_gz(processed_dir / "facility_sites.csv.gz", sites)
    write_csv_gz(processed_dir / "hospital_sites.csv.gz", hospitals)
    verified_fields = [*sites[0].keys(), "verified_hospital_id"]
    write_csv_gz(
        processed_dir / "verified_site_matches.csv.gz",
        verified_matches,
        fieldnames=verified_fields,
    )
    alias_fields = [
        "left_site_id",
        "left_name",
        "right_site_id",
        "right_name",
        "province_reported",
        "city_reported",
        "similarity",
        "decision",
    ]
    write_csv_gz(
        review_dir / "alias_candidates.csv.gz",
        alias_candidates,
        fieldnames=alias_fields,
    )
    _write_registry_gz(package_output, unverified_hospitals, accessed_at=accessed_at)
    hospital_name_scripts = Counter(
        "han" if _HAN_RE.search(site["canonical_reported_name"]) else "latin"
        for site in hospitals
    )
    stats: dict[str, Any] = {
        "source_data_timestamp": source_data_timestamp,
        "total_interventional_studies_with_china_location": total_study_count,
        "studies_with_named_china_facility": len(
            {row["trial_id"] for row in mentions}
        ),
        "facility_mentions": len(mentions),
        "facility_sites": len(sites),
        "hospital_sites": len(hospitals),
        "hospital_sites_missing_reported_province": sum(
            not site["province_reported"] for site in hospitals
        ),
        "hospital_sites_missing_reported_city": sum(
            not site["city_reported"] for site in hospitals
        ),
        "hospital_sites_single_trial": sum(
            site["trial_count"] == 1 for site in hospitals
        ),
        "hospital_sites_ten_or_more_trials": sum(
            site["trial_count"] >= 10 for site in hospitals
        ),
        "hospital_site_names_latin": hospital_name_scripts["latin"],
        "hospital_site_names_han": hospital_name_scripts["han"],
        "verified_site_matches": len(verified_matches),
        "packaged_registry_hospitals": len(unverified_hospitals),
        "alias_candidates_for_review": len(alias_candidates),
    }
    (processed_dir / "snapshot_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return stats


def write_csv_gz(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    fieldnames: list[str] | None = None,
) -> None:
    if not rows and not fieldnames:
        raise ValueError(f"fieldnames are required for an empty CSV snapshot: {path}")
    with _gzip_text_writer(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_registry_gz(
    path: Path, sites: list[dict[str, Any]], *, accessed_at: str
) -> None:
    with _gzip_text_writer(path) as handle:
        for site in sites:
            record = {
                "hospital_id": "cnha-" + site["site_id"],
                "canonical_name": site["canonical_reported_name"],
                "province": site["province_reported"] or "Unknown",
                "city": site["city_reported"] or "Unknown",
                "source_url": site["source_url"],
                "accessed_at": accessed_at,
                "verification_status": "registry_reported",
                "source_registry": site["source_registry"],
                "trial_count": site["trial_count"],
                "aliases": [],
            }
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _verified_location_keys(registry: HospitalRegistry) -> dict[tuple[str, str, str], str]:
    keys: dict[tuple[str, str, str], str] = {}
    for hospital in registry.hospitals:
        names = [hospital.canonical_name, *(alias.name for alias in hospital.aliases)]
        for name in names:
            key = (
                normalize_name(name),
                normalize_name(hospital.province),
                normalize_name(hospital.city),
            )
            keys[key] = hospital.hospital_id
    return keys


def _ngrams(value: str) -> set[str]:
    width = 3 if len(value) >= 5 else 2
    return {value[index : index + width] for index in range(len(value) - width + 1)}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fetch_json(url: str, *, timeout: int, max_retries: int) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "cn-hospital-aliases/0.2 (+public research; low-rate client)",
        },
    )
    for attempt in range(max_retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == max_retries:
                raise
        except URLError:
            if attempt + 1 == max_retries:
                raise
        time.sleep(min(2**attempt, 16))
    raise RuntimeError("unreachable retry state")


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


@contextmanager
def _gzip_text_writer(path: Path) -> Iterator[TextIO]:
    with path.open("wb") as binary:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=binary, mtime=0
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                yield text

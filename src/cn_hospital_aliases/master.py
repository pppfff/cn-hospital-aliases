"""Evidence-preserving institution master data and trial-site linkage.

Exact, location-compatible reference names may link records. Fuzzy candidates
never change identity. Counts are sets of registry-specific trial identifiers.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import csv
from difflib import SequenceMatcher
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .normalizer import normalize_name
from .sources.clinicaltrials_gov import classify_facility, write_csv_gz, _gzip_text_writer

PROVINCES = dict(zip(
    "BJ TJ HE SX NM LN JL HL SH JS ZJ AH FJ JX SD HA HB HN GD GX HI CQ SC GZ YN XZ SN GS QH NX XJ".split(),
    "北京市 天津市 河北省 山西省 内蒙古自治区 辽宁省 吉林省 黑龙江省 上海市 江苏省 浙江省 安徽省 福建省 江西省 山东省 河南省 湖北省 湖南省 广东省 广西壮族自治区 海南省 重庆市 四川省 贵州省 云南省 西藏自治区 陕西省 甘肃省 青海省 宁夏回族自治区 新疆维吾尔自治区".split(),
))
PROVINCE_EN = dict(zip(PROVINCES, "Beijing Tianjin Hebei Shanxi InnerMongolia Liaoning Jilin Heilongjiang Shanghai Jiangsu Zhejiang Anhui Fujian Jiangxi Shandong Henan Hubei Hunan Guangdong Guangxi Hainan Chongqing Sichuan Guizhou Yunnan Tibet Shaanxi Gansu Qinghai Ningxia Xinjiang".split()))
_PROVINCE_KEYS = {normalize_name(name): code for code in PROVINCES for name in (PROVINCES[code], PROVINCE_EN[code])}


def province_key(value: str) -> str:
    text = re.sub(r"\b(province|municipality|autonomous region)\b", "", value, flags=re.I)
    return _PROVINCE_KEYS.get(normalize_name(text), normalize_name(text))


def city_key(value: str) -> str:
    text = re.sub(r"\bcity\b", "", value, flags=re.I).strip().removesuffix("市")
    return normalize_name(text)


def filing_names(value: str) -> list[str]:
    """Read explicitly listed parallel names, retaining unsplittable qualifiers."""
    parts = re.split(r"[（()）、，,;；]", value)
    institutional = re.compile(r"医院|医学院|研究院|研究所|防治中心|妇幼保健")
    names = [part.strip() for part in parts if institutional.search(part.strip())]
    # A parenthetical campus qualifier must not become a hospital identity.
    if any(part.strip() and not institutional.search(part.strip()) for part in parts):
        return [value.strip()]
    return list(dict.fromkeys(names)) or [value.strip()]


def compatible_city(entity: dict, city: str, province: str) -> bool:
    query_city = city_key(city)
    if not query_city or query_city not in entity["city_keys"]:
        return False
    query_province = province_key(province)
    if query_province in PROVINCES and entity["province_code"] and query_province != entity["province_code"]:
        return False
    return True


def _name(entity: dict, value: str, kind: str, source: str, evidence: str, accessed_at: str, **extra) -> None:
    if value.strip():
        entity["names"].append({"name": value.strip(), "kind": kind, "source_url": source, "evidence_status": evidence, "accessed_at": accessed_at, **extra})


def reference_entities(filings: list[dict], ror_records: list[dict], *, accessed_at: str, decisions: dict | None = None) -> dict[str, dict]:
    entities = {}
    decisions = decisions or {}
    excluded = {row["ror_id"] for row in decisions.get("quarantine_ror", [])}
    reviewed_links = {row["ror_id"]: row for row in decisions.get("ror_to_cfdi", [])}
    chinese_index = defaultdict(set)
    for row in filings:
        key = "cnha-cfdi-" + row["companyId"].lower()
        names = filing_names(row["compName"])
        address_cities = set(re.findall(r"([\u4e00-\u9fff]{2,8}市)", row["address"]))
        # Strip a leading province from a Chinese address before city extraction.
        addr = row["address"].removeprefix(row["areaName"])
        city_match = re.match(r"([\u4e00-\u9fff]{2,6}市)", addr)
        city = city_match.group(1) if city_match else (row["areaName"] if row["areaName"] in {"北京市", "上海市", "天津市", "重庆市"} else "")
        entity = {
            "hospital_id": key, "canonical_name": names[0], "official_name_zh": names[0],
            "reference_name_zh": "", "english_name": "", "province": row["areaName"],
            "province_code": province_key(row["areaName"]), "city": city,
            "city_keys": {city_key(city)} if city else set(), "names": [],
            "identifiers": [
                {"scheme": "cfdi_company_id", "value": row["companyId"], "source_url": row["source_url"]},
                {"scheme": "cfdi_drug_filing", "value": row["recordNo"], "source_url": row["source_url"]},
            ],
            "source_url": row["source_url"], "accessed_at": row["accessed_at"],
            "verification_status": "official_filing", "filing_status": {"8": "filed", "9": "cancelled"}.get(row["recordStatus"], row["recordStatus"]),
            "ror_status": "", "website": "", "official_review_completed": False,
        }
        for i, name in enumerate(names):
            _name(entity, name, "canonical" if i == 0 else "parallel_name", row["source_url"], "official_filing", row["accessed_at"])
            chinese_index[normalize_name(name)].add(key)
        entities[key] = entity
    for row in ror_records:
        if row["id"] in excluded:
            continue
        locations = [loc["geonames_details"] for loc in row["locations"] if loc["geonames_details"]["country_code"] == "CN"]
        location = locations[0]
        province_code = location.get("country_subdivision_code", "").removeprefix("CN-")
        names_zh = [name["value"] for name in row["names"] if name.get("lang") == "zh" and "label" in name["types"]]
        names_en = [name["value"] for name in row["names"] if name.get("lang") == "en" and "label" in name["types"]]
        display = next((name["value"] for name in row["names"] if "ror_display" in name["types"]), row["names"][0]["value"])
        candidates = set()
        for name in row["names"]:
            for candidate in chinese_index.get(normalize_name(name["value"]), set()):
                if entities[candidate]["province_code"] == province_code:
                    candidates.add(candidate)
        if row["id"] in reviewed_links:
            reviewed = reviewed_links[row["id"]]
            key = "cnha-cfdi-" + reviewed["cfdi_company_id"].lower()
            if key not in entities or not reviewed.get("source_urls"):
                raise ValueError("Reviewed reference link is missing an identity or source")
            candidates = {key}
        if len(candidates) == 1:
            key = next(iter(candidates))
            # Do not silently combine two distinct ROR records through one filing.
            existing_ror = [item for item in entities[key]["identifiers"] if item["scheme"] == "ror"]
            if existing_ror:
                if row["id"] in reviewed_links:
                    raise ValueError("Reviewed ROR link conflicts with another ROR identity")
                candidates.clear()
        if len(candidates) != 1:
            key = "cnha-ror-" + row["id"].rsplit("/", 1)[-1]
            entities[key] = {
                "hospital_id": key, "canonical_name": names_zh[0] if names_zh else display,
                "official_name_zh": "", "reference_name_zh": "", "english_name": "",
                "province": PROVINCES.get(province_code, location.get("country_subdivision_name", "Unknown")),
                "province_code": province_code, "city": location["name"], "city_keys": set(),
                "names": [], "identifiers": [], "source_url": row["id"], "accessed_at": accessed_at,
                "verification_status": "reference_curated", "filing_status": "not_linked",
                "ror_status": "", "website": "", "official_review_completed": False,
            }
        entity = entities[key]
        entity["reference_name_zh"] = names_zh[0] if names_zh else ""
        entity["english_name"] = names_en[0] if names_en else (display if not re.search(r"[\u4e00-\u9fff]", display) else "")
        entity["ror_status"] = row["status"]
        entity["city_keys"].update(city_key(loc["name"]) for loc in locations)
        entity["identifiers"].append({"scheme": "ror", "value": row["id"], "source_url": row["id"]})
        if key.startswith("cnha-cfdi-"):
            entity["identifiers"].append({"scheme": "legacy_master_id", "value": "cnha-ror-" + row["id"].rsplit("/", 1)[-1], "source_url": row["id"]})
        for ext in row.get("external_ids", []):
            for value in ext["all"]:
                entity["identifiers"].append({"scheme": ext["type"], "value": value, "source_url": row["id"]})
        entity["website"] = next((link["value"] for link in row["links"] if link["type"] == "website"), "")
        for name in row["names"]:
            kind = "common_short_name" if "acronym" in name["types"] else "reference_alias"
            if name.get("lang") == "en" and "label" in name["types"]:
                kind = "english_name"
            _name(entity, name["value"], kind, row["id"], "reference_curated", accessed_at)
    return entities


def expand_website_reviews(document: dict) -> tuple[list[dict], list[dict]]:
    """Expand an explicitly adjudicated website crosswalk, never crawler output."""
    links, reviews = [], []
    for row in document["reviewed_links"]:
        if not all(row.get(field) for field in ("ror_id", "cfdi_company_id", "official_name_zh", "source_url")):
            raise ValueError("Website review needs explicit identities, name and source")
        links.append({"ror_id": row["ror_id"], "cfdi_company_id": row["cfdi_company_id"],
                      "source_urls": [row["source_url"]], "accessed_at": document["accessed_at"],
                      "reason": document["review_scope"]})
        names = [{"value": row["official_name_zh"], "kind": "official_variant"}]
        names.extend({"value": name, "kind": "parallel_name"} for name in row.get("parallel_names", []))
        reviews.append({"hospital_id": "cnha-cfdi-" + row["cfdi_company_id"].lower(),
                        "official_review_completed": False,
                        "names": [{**name, "source_url": row["source_url"], "accessed_at": document["accessed_at"]} for name in names]})
    return links, reviews


def apply_reviews(entities: dict[str, dict], reviews: list[dict]) -> None:
    """Apply explicit field-level evidence only; never infer history from age."""
    for review in reviews:
        entity = entities[review["hospital_id"]]
        entity["city_keys"].update(city_key(city) for city in review.get("city_names", []))
        for name in review.get("names", []):
            if not name.get("source_url") or not name.get("accessed_at"):
                raise ValueError("A reviewed name must carry its own evidence")
            _name(entity, name["value"], name["kind"], name["source_url"], "official_source_reviewed", name["accessed_at"], valid_from=name.get("valid_from"), valid_to=name.get("valid_to"))
            if name["kind"] == "english_name":
                entity["english_name"] = name["value"]
        for identifier in review.get("identifiers", []):
            if not identifier.get("source_url"):
                raise ValueError("Reviewed identifiers require an evidence URL")
            entity["identifiers"].append(identifier)
        entity["official_review_completed"] = review.get("official_review_completed", False)
        if entity["official_review_completed"]:
            official_kinds = {name["kind"] for name in entity["names"] if name["evidence_status"] in {"official_source_reviewed", "seed_source_reviewed"}}
            if not entity["official_name_zh"] or not {"english_name", "common_short_name", "historical_name"} <= official_kinds or not any(item["scheme"] == "cn_uscc" for item in entity["identifiers"]):
                raise ValueError("Completed identity review lacks one of the requested evidence categories")


def apply_verified_seed(entities: dict[str, dict]) -> None:
    from .registry import HospitalRegistry
    index = defaultdict(set)
    for key, entity in entities.items():
        for name in entity["names"]:
            index[(normalize_name(name["name"]), entity["province_code"])].add(key)
    for hospital in HospitalRegistry.load_seed().hospitals:
        possible = set()
        for name in (hospital.canonical_name, *(alias.name for alias in hospital.aliases)):
            possible.update(index.get((normalize_name(name), province_key(hospital.province)), set()))
        if len(possible) != 1:
            continue
        entity = entities[next(iter(possible))]
        _name(entity, hospital.canonical_name, "official_variant", hospital.source_url, "seed_source_reviewed", hospital.accessed_at)
        for alias in hospital.aliases:
            _name(entity, alias.name, alias.kind, alias.source_url, "seed_source_reviewed", hospital.accessed_at, valid_from=alias.valid_from, valid_to=alias.valid_to)
        entity["identifiers"].append({"scheme": "legacy_project_id", "value": hospital.hospital_id, "source_url": hospital.source_url})


def link_mentions(entities: dict[str, dict], mentions: list[dict]) -> tuple[list[dict], dict[str, dict[str, set[str]]]]:
    index = defaultdict(set)
    for key, entity in entities.items():
        for name in entity["names"]:
            index[normalize_name(name["name"])].add(key)
    links = []
    trial_sets = defaultdict(lambda: defaultdict(set))
    for row in mentions:
        if classify_facility(row["facility_name"]) != "hospital" and normalize_name(row["facility_name"]) not in index:
            continue
        candidates = {key for key in index.get(normalize_name(row["facility_name"]), set()) if compatible_city(entities[key], row.get("city_reported", ""), row.get("province_reported", ""))}
        if len(candidates) == 1:
            key, method = next(iter(candidates)), "exact_reference_name_and_city"
        else:
            # Unresolved exact groups are review records, not asserted identities.
            group_key = "\x1f".join((normalize_name(row["facility_name"]), province_key(row.get("province_reported", "")), city_key(row.get("city_reported", ""))))
            key = "cnha-pending-" + hashlib.sha256(group_key.encode()).hexdigest()[:16]
            method = "ambiguous_exact" if candidates else "unresolved"
            if key not in entities:
                entities[key] = {
                    "hospital_id": key, "canonical_name": row["facility_name"], "official_name_zh": "",
                    "reference_name_zh": "", "english_name": "", "province": row.get("province_reported", "") or "Unknown",
                    "province_code": province_key(row.get("province_reported", "")), "city": row.get("city_reported", "") or "Unknown",
                    "city_keys": {city_key(row.get("city_reported", ""))}, "names": [], "identifiers": [],
                    "source_url": row["source_url"], "accessed_at": row.get("accessed_at", "2026-09-04"),
                    "verification_status": "registry_reported", "filing_status": "not_evaluated", "ror_status": "",
                    "website": "", "official_review_completed": False,
                }
        registry = row["source_registry"]
        trial_sets[key][registry].add(row["trial_id"])
        links.append({
            "hospital_id": key, "source_registry": registry, "trial_id": row["trial_id"],
            "reported_name": row["facility_name"], "province_reported": row.get("province_reported", ""),
            "city_reported": row.get("city_reported", ""), "link_method": method,
            "source_url": row["source_url"],
        })
    return links, trial_sets


def build_master(filings: list[dict], ror: list[dict], mentions: list[dict], *, output_dir: Path, package_output: Path, reviews: list[dict], nmpa_records_available: bool, accessed_at: str, decisions: dict | None = None, rank_by: str = "ctg") -> dict:
    if rank_by not in {"ctg", "nmpa"} or (rank_by == "nmpa" and not nmpa_records_available):
        raise ValueError("NMPA ranking requires imported NMPA participation records")
    output_dir.mkdir(parents=True, exist_ok=True)
    entities = reference_entities(filings, ror, accessed_at=accessed_at, decisions=decisions)
    apply_verified_seed(entities)
    apply_reviews(entities, reviews)
    reference_count = len(entities)
    links, counts = link_mentions(entities, mentions)
    rows = []
    for key, entity in entities.items():
        unique_names = {}
        for name in entity["names"]:
            # Retain multiple evidence rows in SQLite; CSV exposes concise names.
            unique_names.setdefault(name["kind"], set()).add(name["name"])
        ctg = len(counts[key]["ClinicalTrials.gov"])
        nmpa = len(counts[key]["NMPA_CDE"]) if nmpa_records_available else None
        identifiers = entity["identifiers"]
        rows.append({
            "hospital_id": key, "canonical_name": entity["canonical_name"],
            "official_name_zh": entity["official_name_zh"], "reference_name_zh": entity["reference_name_zh"],
            "english_name": entity["english_name"], "short_names": " | ".join(sorted(unique_names.get("common_short_name", set()))),
            "historical_names": " | ".join(sorted(unique_names.get("historical_name", set()))),
            "parallel_names": " | ".join(sorted(unique_names.get("parallel_name", set()))),
            "province": entity["province"], "city": entity["city"],
            "ctg_trial_count": ctg, "nmpa_trial_count": nmpa,
            "nmpa_count_scope": "imported_records_only" if nmpa_records_available else "unavailable",
            "filing_number": " | ".join(item["value"] for item in identifiers if item["scheme"] == "cfdi_drug_filing"),
            "ror_id": " | ".join(item["value"] for item in identifiers if item["scheme"] == "ror"),
            "unified_social_credit_code": " | ".join(item["value"] for item in identifiers if item["scheme"] == "cn_uscc"),
            "verification_status": entity["verification_status"], "filing_status": entity["filing_status"],
            "ror_status": entity["ror_status"], "official_review_completed": entity["official_review_completed"],
            "website": entity["website"], "source_url": entity["source_url"], "accessed_at": entity["accessed_at"],
        })
    rank_column = "ctg_trial_count" if rank_by == "ctg" else "nmpa_trial_count"
    rank_scope = "ClinicalTrials.gov snapshot; provisional institution groups" if rank_by == "ctg" else "Supplied NMPA export only; completeness not asserted"
    rows.sort(key=lambda row: (-row[rank_column], row["hospital_id"]))
    priority = []
    for row in rows:
        if row[rank_column] == 0:
            continue
        missing = [field for field in ("official_name_zh", "english_name", "short_names", "historical_names", "unified_social_credit_code") if not row[field]]
        priority.append({"priority_rank": len(priority) + 1, "ranking_basis": rank_by, **row,
                         "review_status": "requested_identity_fields_reviewed" if row["official_review_completed"] else ("official_fields_partially_reviewed" if any(name["evidence_status"] == "official_source_reviewed" for name in entities[row["hospital_id"]]["names"]) else "automated_triage_only"),
                         "fields_to_check": " | ".join(missing), "review_decision": "", "review_evidence_url": "", "review_notes": ""})
        if len(priority) == 1000:
            break
    candidates = suggest_candidates(priority, entities)
    write_csv_gz(output_dir / "institutions.csv.gz", rows)
    write_csv_gz(output_dir / "trial_site_links.csv.gz", links)
    for filename, table in (("top1000_review.csv", priority), ("top1000_candidates.csv", candidates)):
        with (output_dir / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(table[0]) if table else ["hospital_id"])
            writer.writeheader()
            writer.writerows(table)
    _write_sqlite(output_dir / "hospital_master.sqlite", rows, entities, links, priority)
    package_output.parent.mkdir(parents=True, exist_ok=True)
    with _gzip_text_writer(package_output) as handle:
        for row in rows:
            entity = entities[row["hospital_id"]]
            normalized = {normalize_name(entity["canonical_name"])}
            aliases = []
            evidence_order = {"official_source_reviewed": 0, "seed_source_reviewed": 1, "official_filing": 2, "reference_curated": 3}
            for name in sorted(entity["names"], key=lambda item: evidence_order.get(item["evidence_status"], 4)):
                if normalize_name(name["name"]) not in normalized:
                    normalized.add(normalize_name(name["name"]))
                    aliases.append({"name": name["name"], "kind": name["kind"] if name["kind"] != "canonical" else "official_variant", "source_url": name["source_url"], "note": name["evidence_status"], "valid_from": name.get("valid_from"), "valid_to": name.get("valid_to")})
            record = {
                "hospital_id": row["hospital_id"], "canonical_name": row["canonical_name"],
                "province": row["province"] or "Unknown", "city": row["city"] or "Unknown",
                "source_url": row["source_url"], "accessed_at": row["accessed_at"],
                "verification_status": row["verification_status"], "aliases": aliases,
                "trial_count": row["ctg_trial_count"], "source_registry": "Hospital master data",
                "identifiers": entity["identifiers"], "official_name_zh": row["official_name_zh"],
                "english_name": row["english_name"], "nmpa_trial_count": row["nmpa_trial_count"],
                "official_review_completed": row["official_review_completed"],
                "city_aliases": sorted(entity["city_keys"] - {""}),
                "province_aliases": [PROVINCE_EN[entity["province_code"]]] if entity["province_code"] in PROVINCE_EN else [],
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = {
        "built_at": accessed_at, "cfdi_filing_records": len(filings), "ror_china_healthcare_records": len(ror),
        "reference_entities_after_exact_links": reference_count,
        "quarantined_ror_records": len((decisions or {}).get("quarantine_ror", [])),
        "quarantined_ror_ids": [row["ror_id"] for row in (decisions or {}).get("quarantine_ror", [])],
        "cfdi_ror_linked_entities": sum(bool(row["filing_number"] and row["ror_id"]) for row in rows),
        "ctg_trial_ids_in_input": len({row["trial_id"] for row in mentions if row["source_registry"] == "ClinicalTrials.gov"}),
        "nmpa_trial_ids_in_input": len({row["trial_id"] for row in mentions if row["source_registry"] == "NMPA_CDE"}) if nmpa_records_available else None,
        "nmpa_participation_coverage": "partial_import" if nmpa_records_available else "blocked_no_trial_detail_data",
        "master_rows_including_unresolved_groups": len(rows),
        "participation_rows": len(links), "exact_reference_linked_rows": sum(row["link_method"] == "exact_reference_name_and_city" for row in links),
        "top1000_rows": len(priority), "top1000_with_official_chinese_name": sum(bool(row["official_name_zh"]) for row in priority),
        "top1000_with_english_name": sum(bool(row["english_name"]) for row in priority),
        "top1000_with_ror_id": sum(bool(row["ror_id"]) for row in priority),
        "top1000_with_filing_id": sum(bool(row["filing_number"]) for row in priority),
        "top1000_fully_official_reviewed": sum(row["official_review_completed"] for row in priority),
        "official_field_reviewed_entities": sum(any(name["evidence_status"] == "official_source_reviewed" for name in entity["names"]) for entity in entities.values()),
        "top1000_with_official_field_review": sum(row["review_status"] != "automated_triage_only" for row in priority),
        "top1000_with_official_english_evidence": sum(any(name["kind"] == "english_name" and name["evidence_status"] == "official_source_reviewed" for name in entities[row["hospital_id"]]["names"]) for row in priority),
        "top1000_with_short_name": sum(bool(row["short_names"]) for row in priority),
        "top1000_with_historical_name": sum(bool(row["historical_names"]) for row in priority),
        "top1000_with_uscc": sum(bool(row["unified_social_credit_code"]) for row in priority),
        "fuzzy_candidates_not_merged": len(candidates),
        "ranking_scope": rank_scope,
        "ranking_basis": rank_by,
        "cross_registry_trial_deduplication": "not asserted; keep NCT and CTR counts separate",
    }
    (output_dir / "quality_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def suggest_candidates(priority: list[dict], entities: dict[str, dict]) -> list[dict]:
    by_city = defaultdict(list)
    for key, entity in entities.items():
        if entity["verification_status"] == "registry_reported":
            continue
        names = {normalize_name(name["name"]): name["name"] for name in entity["names"]}
        for city in entity["city_keys"]:
            by_city[city].append((key, names))
    candidates = []
    for row in priority:
        if row["verification_status"] != "registry_reported":
            continue
        query = normalize_name(row["canonical_name"])
        matches = []
        for key, names in by_city.get(city_key(row["city"]), []):
            best = (0.0, "")
            for normalized, original in names.items():
                if min(len(query), len(normalized)) / max(len(query), len(normalized), 1) < 0.6:
                    continue
                score = SequenceMatcher(None, query, normalized, autojunk=False).ratio()
                if score > best[0]:
                    best = (score, original)
            if best[0] >= 0.8:
                matches.append((best[0], key, best[1]))
        for score, key, matched_name in sorted(matches, reverse=True)[:3]:
            candidates.append({"priority_rank": row["priority_rank"], "hospital_id": row["hospital_id"], "reported_name": row["canonical_name"], "candidate_hospital_id": key, "candidate_canonical_name": entities[key]["canonical_name"], "matched_reference_name": matched_name, "similarity": round(score, 6), "decision": "review_required", "source_url": entities[key]["source_url"]})
    return candidates


def _write_sqlite(path: Path, rows: list[dict], entities: dict[str, dict], links: list[dict], priority: list[dict]) -> None:
    temporary = path.with_suffix(".sqlite.tmp")
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(temporary)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        cols = list(rows[0])
        types = {"ctg_trial_count": "INTEGER", "nmpa_trial_count": "INTEGER", "official_review_completed": "INTEGER"}
        definitions = ",".join(f'"{col}" {types.get(col, "TEXT")}' + (" PRIMARY KEY" if col == "hospital_id" else "") for col in cols)
        connection.execute(f"CREATE TABLE institutions ({definitions})")
        marks = ",".join("?" for _ in cols)
        connection.executemany(f"INSERT INTO institutions VALUES ({marks})", [[row[col] for col in cols] for row in rows])
        connection.execute("CREATE TABLE names (hospital_id TEXT REFERENCES institutions, name TEXT, kind TEXT, evidence_status TEXT, source_url TEXT, accessed_at TEXT, valid_from TEXT, valid_to TEXT)")
        connection.execute("CREATE TABLE identifiers (hospital_id TEXT REFERENCES institutions, scheme TEXT, value TEXT, source_url TEXT, UNIQUE(hospital_id,scheme,value))")
        connection.execute("CREATE TABLE trial_site_links (hospital_id TEXT REFERENCES institutions, source_registry TEXT, trial_id TEXT, reported_name TEXT, province_reported TEXT, city_reported TEXT, link_method TEXT, source_url TEXT)")
        connection.execute("CREATE TABLE review_priority (priority_rank INTEGER PRIMARY KEY, hospital_id TEXT REFERENCES institutions, review_status TEXT, fields_to_check TEXT)")
        for key, entity in entities.items():
            connection.executemany("INSERT INTO names VALUES (?,?,?,?,?,?,?,?)", [(key, n["name"], n["kind"], n["evidence_status"], n["source_url"], n["accessed_at"], n.get("valid_from"), n.get("valid_to")) for n in entity["names"]])
            connection.executemany("INSERT OR IGNORE INTO identifiers VALUES (?,?,?,?)", [(key, n["scheme"], n["value"], n["source_url"]) for n in entity["identifiers"]])
        connection.executemany("INSERT INTO trial_site_links VALUES (?,?,?,?,?,?,?,?)", [[row[col] for col in ("hospital_id", "source_registry", "trial_id", "reported_name", "province_reported", "city_reported", "link_method", "source_url")] for row in links])
        connection.executemany("INSERT INTO review_priority VALUES (?,?,?,?)", [[row[col] for col in ("priority_rank", "hospital_id", "review_status", "fields_to_check")] for row in priority])
        connection.execute("CREATE INDEX names_lookup ON names(name)")
        connection.execute("CREATE INDEX trial_lookup ON trial_site_links(hospital_id, source_registry, trial_id)")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Master database contains orphan rows")
    temporary.replace(path)

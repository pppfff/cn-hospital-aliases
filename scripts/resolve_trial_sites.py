"""Resolve a trial-site CSV against official filing identities.

Required input column: facility_name (or the Chinese 机构名称). Optional
province_reported/city_reported columns are used only as disambiguation filters.
"""
import argparse
import csv
from pathlib import Path

from cn_hospital_aliases import HospitalRegistry


def resolve(input_path: Path, output_path: Path, *, fuzzy: bool = False) -> dict:
    registry = HospitalRegistry.load_default()
    with input_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header")
        name_column = next((column for column in ("facility_name", "机构名称", "hospital_name", "医院名称") if column in reader.fieldnames), None)
        if not name_column:
            raise ValueError("Input CSV needs facility_name, 机构名称, hospital_name or 医院名称")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("Input CSV has inconsistent row width; quote names containing commas")
    output_fields = list(reader.fieldnames) + ["resolution_status", "official_hospital_id", "official_name_zh", "filing_number", "filing_status", "matched_alias", "match_type", "match_score", "candidate_count"]
    counts = {"matched": 0, "ambiguous": 0, "unmatched": 0, "fuzzy_candidate": 0}
    for row in rows:
        matches = registry.resolve(row.get(name_column, ""), province=row.get("province_reported") or row.get("省份"), city=row.get("city_reported") or row.get("城市"), fuzzy=fuzzy)
        status = "matched" if len(matches) == 1 and matches[0].match_type != "fuzzy" else ("fuzzy_candidate" if matches and matches[0].match_type == "fuzzy" else ("ambiguous" if matches else "unmatched"))
        counts[status] += 1
        chosen = matches[0] if status == "matched" else None
        row.update({"resolution_status": status, "official_hospital_id": chosen.hospital.hospital_id if chosen else "", "official_name_zh": chosen.hospital.official_name_zh or chosen.hospital.canonical_name if chosen else "", "filing_number": chosen.hospital.filing_number if chosen else "", "filing_status": chosen.hospital.filing_status if chosen else "", "matched_alias": chosen.matched_name if chosen else "", "match_type": chosen.match_type if chosen else "", "match_score": f"{chosen.score:.6f}" if chosen else "", "candidate_count": str(len(matches))})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)
    return {"input_rows": len(rows), **counts, "fuzzy_is_approval": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fuzzy", action="store_true", help="emit fuzzy candidates without approving them")
    args = parser.parse_args()
    print(resolve(args.input, args.output, fuzzy=args.fuzzy))

"""Command-line interface for hospital-name resolution."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

from .registry import HospitalRegistry
from .validation import validate_hospitals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cn-hospital-alias")
    dataset = parser.add_mutually_exclusive_group()
    dataset.add_argument("--official", action="store_true", help="use official filing identities and approved aliases (default)")
    dataset.add_argument("--seed", action="store_true", help="use the original six-hospital examples")
    dataset.add_argument("--data", type=Path, help="custom hospital JSONL file")
    dataset.add_argument("--master", action="store_true", help="use the evidence-linked institution master")
    dataset.add_argument(
        "--include-trial-sites",
        action="store_true",
        help="include the generated registry-reported trial-site snapshot",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="resolve one hospital name")
    resolve.add_argument("name")
    _add_match_options(resolve)
    resolve.add_argument("--json", action="store_true", help="emit JSON")

    batch = subparsers.add_parser("batch", help="resolve a CSV column")
    batch.add_argument("input", type=Path)
    batch.add_argument("output", type=Path)
    batch.add_argument("--column", default="hospital_name")
    batch.add_argument("--province-column")
    batch.add_argument("--city-column")
    _add_match_options(batch, include_location=False)

    subparsers.add_parser("stats", help="show bundled dataset statistics")
    validate = subparsers.add_parser("validate", help="validate hospital records")
    validate.add_argument(
        "--summary-only", action="store_true", help="do not print individual warnings"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.data:
            registry = HospitalRegistry.from_jsonl(args.data)
        elif args.master:
            registry = HospitalRegistry.load_master()
        elif args.include_trial_sites:
            registry = HospitalRegistry.load_all()
        elif args.seed:
            registry = HospitalRegistry.load_seed()
        else:
            registry = HospitalRegistry.load_default()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "resolve":
        matches = registry.resolve(
            args.name,
            province=args.province,
            city=args.city,
            fuzzy=args.fuzzy,
            min_score=args.min_score,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps([match.to_dict() for match in matches], ensure_ascii=False, indent=2))
        else:
            _print_matches(matches)
        return 0 if len(matches) == 1 else (1 if not matches else 3)

    if args.command == "batch":
        return _run_batch(registry, args)

    if args.command == "stats":
        aliases = sum(len(hospital.aliases) for hospital in registry.hospitals)
        verified = sum(
            hospital.verification_status == "verified"
            for hospital in registry.hospitals
        )
        print(f"hospitals\t{len(registry.hospitals)}")
        print(f"verified_hospitals\t{verified}")
        statuses = Counter(hospital.verification_status for hospital in registry.hospitals)
        for status in ("registry_reported", "official_filing", "reference_curated"):
            print(f"{status}_hospitals\t{statuses[status]}")
        print(f"aliases\t{aliases}")
        print(f"collisions\t{len(registry.alias_collisions())}")
        return 0

    report = validate_hospitals(registry.hospitals)
    if not args.summary_only:
        for warning in report.warnings:
            print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    print(
        f"validated {len(registry.hospitals)} hospitals: "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    return 0 if report.ok else 2


def _add_match_options(
    parser: argparse.ArgumentParser, *, include_location: bool = True
) -> None:
    if include_location:
        parser.add_argument("--province")
        parser.add_argument("--city")
    parser.add_argument("--fuzzy", action="store_true")
    parser.add_argument("--min-score", type=float, default=0.78)
    parser.add_argument("--limit", type=int, default=5)


def _print_matches(matches: list[object]) -> None:
    if not matches:
        print("no match")
        return
    print("canonical_name\thospital_id\tmatched_name\tmatch_type\talias_kind\tscore")
    for match in matches:
        print(
            f"{match.hospital.canonical_name}\t{match.hospital.hospital_id}\t"
            f"{match.matched_name}\t{match.match_type}\t{match.alias_kind}\t"
            f"{match.score:.3f}"
        )


def _run_batch(registry: HospitalRegistry, args: argparse.Namespace) -> int:
    try:
        with args.input.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None or args.column not in reader.fieldnames:
                print(f"error: CSV column not found: {args.column}", file=sys.stderr)
                return 2
            rows = list(reader)
            input_fields = list(reader.fieldnames)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                print("error: inconsistent CSV row width; quote hospital names containing commas", file=sys.stderr)
                return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_fields = input_fields + [
        "_resolution_status",
        "_hospital_id",
        "_canonical_name",
        "_matched_name",
        "_match_type",
        "_match_score",
        "_candidate_count",
        "_filing_number",
        "_filing_status",
    ]
    for row in rows:
        province = row.get(args.province_column) if args.province_column else None
        city = row.get(args.city_column) if args.city_column else None
        matches = registry.resolve(
            row.get(args.column, ""),
            province=province or None,
            city=city or None,
            fuzzy=args.fuzzy,
            min_score=args.min_score,
            limit=args.limit,
        )
        status = "matched" if len(matches) == 1 else ("unmatched" if not matches else "ambiguous")
        if matches and matches[0].match_type == "fuzzy":
            status = "fuzzy_candidate"
        chosen = matches[0] if status == "matched" else None
        row.update(
            {
                "_resolution_status": status,
                "_hospital_id": chosen.hospital.hospital_id if chosen else "",
                "_canonical_name": chosen.hospital.canonical_name if chosen else "",
                "_matched_name": chosen.matched_name if chosen else "",
                "_match_type": chosen.match_type if chosen else "",
                "_match_score": f"{chosen.score:.6f}" if chosen else "",
                "_candidate_count": str(len(matches)),
                "_filing_number": (chosen.hospital.filing_number or "") if chosen else "",
                "_filing_status": (chosen.hospital.filing_status or "") if chosen else "",
            }
        )

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=output_fields)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(rows)} row(s) to {args.output}")
    return 0

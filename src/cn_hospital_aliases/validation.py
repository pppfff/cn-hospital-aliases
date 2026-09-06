"""Dataset quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from .models import Hospital
from .normalizer import normalize_name


ALIAS_KINDS = {
    "official_variant",
    "common_short_name",
    "parallel_name",
    "historical_name",
    "english_name",
    "registry_variant",
    "reference_alias",
}

VERIFICATION_STATUSES = {"verified", "registry_reported", "official_filing", "reference_curated"}


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_hospitals(hospitals: tuple[Hospital, ...]) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    name_to_ids: dict[str, set[str]] = {}

    for hospital in hospitals:
        prefix = hospital.hospital_id or "<missing-id>"
        if not hospital.hospital_id.startswith("cnha-"):
            errors.append(f"{prefix}: hospital_id must start with cnha-")
        if hospital.hospital_id in seen_ids:
            errors.append(f"{prefix}: duplicate hospital_id")
        seen_ids.add(hospital.hospital_id)
        for field_name in ("canonical_name", "province", "city"):
            if not getattr(hospital, field_name).strip():
                errors.append(f"{prefix}: {field_name} must not be empty")
        if not _valid_source_url(hospital.source_url):
            errors.append(f"{prefix}: source_url must be an HTTP(S) URL")
        if hospital.verification_status not in VERIFICATION_STATUSES:
            errors.append(
                f"{prefix}: unsupported verification_status "
                f"{hospital.verification_status!r}"
            )
        if hospital.trial_count is not None and hospital.trial_count < 0:
            errors.append(f"{prefix}: trial_count must be non-negative when present")
        try:
            date.fromisoformat(hospital.accessed_at)
        except ValueError:
            errors.append(f"{prefix}: accessed_at must be an ISO date")

        local_names: set[str] = set()
        all_names = [(hospital.canonical_name, "canonical", hospital.source_url)] + [
            (alias.name, alias.kind, alias.source_url) for alias in hospital.aliases
        ]
        for name, kind, source_url in all_names:
            key = normalize_name(name)
            if not key:
                errors.append(f"{prefix}: empty canonical name or alias")
                continue
            if key in local_names:
                errors.append(f"{prefix}: duplicate normalized name {name!r}")
            local_names.add(key)
            name_to_ids.setdefault(key, set()).add(hospital.hospital_id)
            if kind != "canonical" and kind not in ALIAS_KINDS:
                errors.append(f"{prefix}: unsupported alias kind {kind!r}")
            if not _valid_source_url(source_url):
                errors.append(f"{prefix}: source URL for {name!r} must use HTTP(S)")
            elif source_url.startswith("http://"):
                warnings.append(f"{prefix}: source for {name!r} uses legacy HTTP; verify current official ownership")

    for key, hospital_ids in sorted(name_to_ids.items()):
        if len(hospital_ids) > 1:
            warnings.append(
                f"normalized name {key!r} maps to multiple hospitals: "
                + ", ".join(sorted(hospital_ids))
            )
    return ValidationReport(tuple(errors), tuple(warnings))


def _valid_source_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username and not parsed.password

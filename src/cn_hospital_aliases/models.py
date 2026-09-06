"""Typed data objects used by the resolver."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Alias:
    name: str
    kind: str
    source_url: str
    valid_from: str | None = None
    valid_to: str | None = None
    note: str | None = None
    accessed_at: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Alias":
        return cls(
            name=value["name"],
            kind=value["kind"],
            source_url=value["source_url"],
            valid_from=value.get("valid_from"),
            valid_to=value.get("valid_to"),
            note=value.get("note"),
            accessed_at=value.get("accessed_at"),
        )


@dataclass(frozen=True, slots=True)
class Hospital:
    hospital_id: str
    canonical_name: str
    province: str
    city: str
    source_url: str
    accessed_at: str
    aliases: tuple[Alias, ...] = ()
    district: str | None = None
    verification_status: str = "verified"
    source_registry: str | None = None
    trial_count: int | None = None
    identifiers: tuple[dict[str, str], ...] = ()
    official_name_zh: str | None = None
    english_name: str | None = None
    nmpa_trial_count: int | None = None
    official_review_completed: bool = False
    city_aliases: tuple[str, ...] = ()
    province_aliases: tuple[str, ...] = ()
    filing_number: str | None = None
    filing_status: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Hospital":
        return cls(
            hospital_id=value["hospital_id"],
            canonical_name=value["canonical_name"],
            province=value["province"],
            city=value["city"],
            district=value.get("district"),
            source_url=value["source_url"],
            accessed_at=value["accessed_at"],
            aliases=tuple(Alias.from_dict(alias) for alias in value.get("aliases", [])),
            verification_status=value.get("verification_status", "verified"),
            source_registry=value.get("source_registry"),
            trial_count=value.get("trial_count"),
            identifiers=tuple(value.get("identifiers", [])),
            official_name_zh=value.get("official_name_zh"),
            english_name=value.get("english_name"),
            nmpa_trial_count=value.get("nmpa_trial_count"),
            official_review_completed=value.get("official_review_completed", False),
            city_aliases=tuple(value.get("city_aliases", [])),
            province_aliases=tuple(value.get("province_aliases", [])),
            filing_number=value.get("filing_number"),
            filing_status=value.get("filing_status"),
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    hospital: Hospital
    matched_name: str
    match_type: str
    alias_kind: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["score"] = round(self.score, 6)
        return value

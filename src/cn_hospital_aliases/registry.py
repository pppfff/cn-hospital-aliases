"""Hospital registry loading and identity resolution."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import gzip
from importlib import resources
import json
from pathlib import Path
from typing import Iterable

from .models import Alias, Hospital, MatchResult
from .normalizer import normalize_name


class NotFoundError(LookupError):
    """Raised when no hospital candidate is found."""


class AmbiguousNameError(LookupError):
    """Raised when a name resolves to more than one hospital."""

    def __init__(self, query: str, matches: list[MatchResult]):
        self.query = query
        self.matches = matches
        names = ", ".join(match.hospital.canonical_name for match in matches)
        super().__init__(f"ambiguous hospital name {query!r}: {names}")


class HospitalRegistry:
    """An immutable in-memory index of hospital identities and aliases."""

    def __init__(self, hospitals: Iterable[Hospital]):
        self.hospitals = tuple(hospitals)
        if not self.hospitals:
            raise ValueError("registry must contain at least one hospital")

        hospital_ids: set[str] = set()
        index: dict[str, list[tuple[Hospital, Alias | None]]] = defaultdict(list)
        for hospital in self.hospitals:
            if hospital.hospital_id in hospital_ids:
                raise ValueError(f"duplicate hospital_id: {hospital.hospital_id}")
            hospital_ids.add(hospital.hospital_id)
            index[normalize_name(hospital.canonical_name)].append((hospital, None))
            for alias in hospital.aliases:
                index[normalize_name(alias.name)].append((hospital, alias))
        self._index = dict(index)
        identifier_index = defaultdict(set)
        self._by_id = {hospital.hospital_id: hospital for hospital in self.hospitals}
        for hospital in self.hospitals:
            identifier_index[("hospital_id", hospital.hospital_id)].add(hospital.hospital_id)
            for identifier in hospital.identifiers:
                identifier_index[(identifier["scheme"], identifier["value"])].add(hospital.hospital_id)
        self._identifier_index = dict(identifier_index)

    def resolve_identifier(self, scheme: str, value: str) -> tuple[Hospital, ...]:
        """Look up an exact identifier without assuming all schemes are unique."""
        return tuple(self._by_id[key] for key in sorted(self._identifier_index.get((scheme, value), ())))

    @classmethod
    def load_default(cls) -> "HospitalRegistry":
        """Use official filing identities and approved aliases by default."""
        return cls.load_official()

    @classmethod
    def load_official(cls) -> "HospitalRegistry":
        data_file = resources.files("cn_hospital_aliases.data").joinpath("official_site_aliases.jsonl.gz")
        with data_file.open("rb") as binary_handle:
            with gzip.open(binary_handle, "rt", encoding="utf-8") as handle:
                return cls(_read_jsonl(handle))

    @classmethod
    def load_seed(cls) -> "HospitalRegistry":
        """Load the original six-hospital examples, not the production registry."""
        data_file = resources.files("cn_hospital_aliases.data").joinpath(
            "hospitals.jsonl"
        )
        with data_file.open("r", encoding="utf-8") as handle:
            return cls(_read_jsonl(handle))

    @classmethod
    def load_trial_sites(cls) -> "HospitalRegistry":
        """Load the generated ClinicalTrials.gov hospital-candidate snapshot."""

        data_file = resources.files("cn_hospital_aliases.data").joinpath(
            "clinical_trial_hospitals.jsonl.gz"
        )
        with data_file.open("rb") as binary_handle:
            with gzip.open(binary_handle, "rt", encoding="utf-8") as handle:
                return cls(_read_jsonl(handle))

    @classmethod
    def load_master(cls) -> "HospitalRegistry":
        """Load evidence-linked CFDI/ROR identities and unresolved trial groups."""
        data_file = resources.files("cn_hospital_aliases.data").joinpath("hospital_master.jsonl.gz")
        with data_file.open("rb") as binary_handle:
            with gzip.open(binary_handle, "rt", encoding="utf-8") as handle:
                return cls(_read_jsonl(handle))

    @classmethod
    def load_all(cls) -> "HospitalRegistry":
        """Load verified records plus registry-reported trial-site candidates."""

        verified = cls.load_seed()
        trial_sites = cls.load_trial_sites()
        return cls((*verified.hospitals, *trial_sites.hospitals))

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "HospitalRegistry":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(_read_jsonl(handle))

    def resolve(
        self,
        query: str,
        *,
        province: str | None = None,
        city: str | None = None,
        fuzzy: bool = False,
        min_score: float = 0.78,
        limit: int = 5,
    ) -> list[MatchResult]:
        """Resolve a name, returning all exact matches or ranked fuzzy candidates."""

        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between 0 and 1")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        query_key = normalize_name(query)
        if not query_key:
            return []

        exact = self._exact_matches(query_key, province=province, city=city)
        if exact or not fuzzy:
            # Truncating exact matches can turn an ambiguous name into a false
            # unique match in get_one() or batch resolution.
            return exact

        best_by_hospital: dict[str, MatchResult] = {}
        for candidate_key, entries in self._index.items():
            score = SequenceMatcher(None, query_key, candidate_key).ratio()
            if score < min_score:
                continue
            for hospital, alias in entries:
                if not _location_matches(hospital, province=province, city=city):
                    continue
                result = MatchResult(
                    hospital=hospital,
                    matched_name=alias.name if alias else hospital.canonical_name,
                    match_type="fuzzy",
                    alias_kind=alias.kind if alias else "canonical",
                    score=score,
                )
                current = best_by_hospital.get(hospital.hospital_id)
                if current is None or result.score > current.score:
                    best_by_hospital[hospital.hospital_id] = result

        ranked = sorted(
            best_by_hospital.values(),
            key=lambda item: (-item.score, item.hospital.canonical_name),
        )
        return ranked[:limit]

    def get_one(self, query: str, **kwargs: object) -> MatchResult:
        """Return exactly one result or raise a typed lookup error."""

        if kwargs.get("fuzzy"):
            kwargs["limit"] = max(2, int(kwargs.get("limit", 5)))
        matches = self.resolve(query, **kwargs)
        if not matches:
            raise NotFoundError(f"hospital name not found: {query!r}")
        if len(matches) > 1:
            raise AmbiguousNameError(query, matches)
        return matches[0]

    def alias_collisions(self) -> dict[str, tuple[str, ...]]:
        """Return normalized names that point to multiple hospital identities."""

        collisions: dict[str, tuple[str, ...]] = {}
        for key, entries in self._index.items():
            hospital_ids = tuple(sorted({entry[0].hospital_id for entry in entries}))
            if len(hospital_ids) > 1:
                collisions[key] = hospital_ids
        return collisions

    def _exact_matches(
        self, query_key: str, *, province: str | None, city: str | None
    ) -> list[MatchResult]:
        best_by_hospital: dict[str, MatchResult] = {}
        for hospital, alias in self._index.get(query_key, []):
            if not _location_matches(hospital, province=province, city=city):
                continue
            result = MatchResult(
                hospital=hospital,
                matched_name=alias.name if alias else hospital.canonical_name,
                match_type="canonical" if alias is None else "alias",
                alias_kind="canonical" if alias is None else alias.kind,
                score=1.0,
            )
            current = best_by_hospital.get(hospital.hospital_id)
            if current is None or result.match_type == "canonical":
                best_by_hospital[hospital.hospital_id] = result
        return sorted(
            best_by_hospital.values(), key=lambda item: item.hospital.canonical_name
        )


def _read_jsonl(handle: Iterable[str]) -> list[Hospital]:
    hospitals: list[Hospital] = []
    for line_number, line in enumerate(handle, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            value = json.loads(stripped)
            hospitals.append(Hospital.from_dict(value))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid hospital JSONL at line {line_number}: {exc}") from exc
    return hospitals


def _location_matches(
    hospital: Hospital, *, province: str | None, city: str | None
) -> bool:
    if province and normalize_name(province) not in {normalize_name(value) for value in (hospital.province, *hospital.province_aliases)}:
        return False
    if city and normalize_name(city) not in {normalize_name(value) for value in (hospital.city, *hospital.city_aliases)}:
        return False
    return True

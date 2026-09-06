"""Canonical-name and alias resolution for Chinese hospitals."""

from .models import Alias, Hospital, MatchResult
from .normalizer import normalize_name
from .registry import AmbiguousNameError, HospitalRegistry, NotFoundError

__all__ = [
    "Alias",
    "AmbiguousNameError",
    "Hospital",
    "HospitalRegistry",
    "MatchResult",
    "NotFoundError",
    "normalize_name",
]

__version__ = "0.4.0"

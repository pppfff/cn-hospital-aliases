"""Conservative normalization that does not erase institutional identity."""

from __future__ import annotations

import re
import unicodedata


_IGNORED = re.compile(r"[\s\u3000,，。.;；:：'\"“”‘’`·•・_\-—–/\\()（）\[\]【】{}]+")


def normalize_name(name: str) -> str:
    """Return a conservative comparison key for a hospital name.

    Unicode width, Latin case, whitespace, and presentation punctuation are
    normalized. Semantic words and administrative prefixes are retained.
    """

    if not isinstance(name, str):
        raise TypeError("hospital name must be a string")
    normalized = unicodedata.normalize("NFKC", name).casefold().strip()
    return _IGNORED.sub("", normalized)


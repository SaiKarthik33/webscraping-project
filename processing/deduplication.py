"""Duplicate detection with normalised fingerprints."""
import hashlib
import re

from processing.constants import BOOKS_SOURCE


def _normalize(value):
    """Lowercase, drop punctuation, collapse whitespace."""
    text = re.sub(r"[^\w\s]", "", str(value or "").lower())
    return " ".join(text.split())


def make_fingerprint(rec):
    """Hash of the identifying fields.

    Books : source + title
    Quotes: source + author + first 50 characters of the quote text
    The 50-character cut is applied AFTER normalising, so spacing or
    punctuation differences at the start of a quote cannot hide a duplicate.
    """
    source = _normalize(rec.get("source"))
    title = _normalize(rec.get("name_or_title"))
    if rec.get("source") == BOOKS_SOURCE:
        key = f"{source}|{title}"
    else:  # quotes
        key = f"{source}|{_normalize(rec.get('author'))}|{title[:50]}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def find_duplicates(records):
    """Split records into (unique, duplicates). The first occurrence is kept."""
    seen, unique, dupes = set(), [], []
    for rec in records:
        fingerprint = make_fingerprint(rec)
        if fingerprint in seen:
            dupes.append(rec)
        else:
            seen.add(fingerprint)
            unique.append(rec)
    return unique, dupes

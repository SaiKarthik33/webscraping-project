"""Small, pure cleaning functions: take a value, return a cleaned value.

No internet and no files here, so every function can be tested with a plain string.
"""
import re
from urllib.parse import urljoin

from processing.constants import BOOKS_SOURCE, COLUMNS, QUOTES_SOURCE

RATING_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Curly quotes used by Quotes to Scrape, plus the plain double quote.
_QUOTE_CHARS = "\u201c\u201d\""


def clean_text(value):
    """Collapse tabs, newlines, non-breaking spaces and repeated spaces. '' -> None."""
    if value is None:
        return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    return text or None


def strip_quotes(value):
    """Remove the curly quotation marks wrapped around a quote's text."""
    text = clean_text(value)
    if text is None:
        return None
    return clean_text(text.strip(_QUOTE_CHARS))


def clean_price(raw):
    """'£51.77' -> 51.77. Returns None if no number can be found."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(match.group()) if match else None


def clean_rating(raw):
    """'star-rating Three' -> 3. Also accepts '4' or 4. Returns None if nothing matches.

    Out-of-range digits (e.g. '7') are returned as-is so validation can reject them.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    for token in str(raw).lower().split():
        if token in RATING_MAP:
            return RATING_MAP[token]
        if token.isdigit():
            return int(token)
    return None


def clean_tags(tags):
    """['Love', ' life '] -> 'life;love' (lowercase, de-duplicated, sorted, ';'-joined)."""
    if tags is None:
        return None
    parts = re.split(r"[;,]", tags) if isinstance(tags, str) else tags
    cleaned = set()
    for tag in parts:
        text = clean_text(tag)
        if text:
            cleaned.add(text.lower().replace(";", ","))
    return ";".join(sorted(cleaned)) or None


def normalize_url(url, base=None):
    """Trim the URL and make it absolute when a base URL is given.

    This is best effort: validation (not this function) rejects anything that
    still does not start with http:// or https://.
    """
    text = clean_text(url)
    if text is None:
        return None
    return urljoin(base, text) if base else text


def _keep_unparsed(cleaned, raw):
    """If a value was present but could not be parsed, keep the raw text.

    That way validation can reject it with a clear reason instead of the
    problem silently turning into an empty cell.
    """
    if cleaned is not None:
        return cleaned
    return clean_text(raw) if isinstance(raw, str) else None


def clean_record(raw):
    """Turn one raw scraped dict into one record of the common data model."""
    source = clean_text(raw.get("source"))
    record = {column: None for column in COLUMNS}
    record["source"] = source
    record["source_url"] = normalize_url(raw.get("source_url"))
    record["scraped_at"] = clean_text(raw.get("scraped_at"))

    if source == BOOKS_SOURCE:
        record["name_or_title"] = clean_text(raw.get("title"))
        record["category"] = clean_text(raw.get("category_raw"))
        record["price"] = _keep_unparsed(clean_price(raw.get("price_raw")), raw.get("price_raw"))
        record["rating"] = _keep_unparsed(clean_rating(raw.get("rating_raw")), raw.get("rating_raw"))
        record["description"] = clean_text(raw.get("description_raw"))
    elif source == QUOTES_SOURCE:
        record["name_or_title"] = strip_quotes(raw.get("text_raw"))
        record["author"] = clean_text(raw.get("author_raw"))
        record["tags"] = clean_tags(raw.get("tags_raw"))
    else:  # unknown source: map generically; validation rejects it as 'unknown_source'
        record["name_or_title"] = clean_text(raw.get("title") or raw.get("text_raw"))
    return record

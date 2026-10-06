"""Record validation. Returns the list of problems found (empty list = valid)."""
import math

from processing.constants import VALID_SOURCES

# Every reason this module can return (used to pre-fill the summary report with zeros).
VALIDATION_REASONS = (
    "unknown_source",
    "missing_name",
    "invalid_url",
    "invalid_price",
    "invalid_rating",
)


def validate_record(rec):
    problems = []

    if rec.get("source") not in VALID_SOURCES:
        problems.append("unknown_source")

    if not rec.get("name_or_title"):
        problems.append("missing_name")

    url = str(rec.get("source_url") or "").lower()
    if not url.startswith(("http://", "https://")):
        problems.append("invalid_url")

    price = rec.get("price")
    if price is not None:
        is_number = isinstance(price, (int, float)) and not isinstance(price, bool)
        if not is_number or not math.isfinite(price) or price < 0:
            problems.append("invalid_price")

    rating = rec.get("rating")
    if rating is not None:
        is_int = isinstance(rating, int) and not isinstance(rating, bool)
        if not is_int or rating not in (1, 2, 3, 4, 5):
            problems.append("invalid_rating")

    return problems

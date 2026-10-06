import argparse
import csv
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from processing.cleaning import clean_record
from processing.constants import COLUMNS
from processing.deduplication import find_duplicates
from processing.validation import VALIDATION_REASONS, validate_record
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

# Reasons a record can be rejected: the validation rules + two pipeline-level ones.
ALL_REASONS = VALIDATION_REASONS + ("parse_error", "cleaning_error")

logger = logging.getLogger("main")


# --------------------------------------------------------------------------- logging
def configure_logging(log_dir: Path = LOG_DIR) -> None:
    """Configure logging once: console (INFO) and logs/scraper.log (DEBUG, overwritten each run)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):  # avoid UnicodeEncodeError on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(log_dir / "scraper.log", mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


# --------------------------------------------------------------------------- stages
def new_stats(status: str) -> dict:
    return {
        "status": status,
        "stop_reason": "",
        "pages_fetched": 0,
        "pages_failed": 0,
        "raw_collected": 0,
        "cleaned": 0,
        "rejected_records": 0,
        "rejected_by_reason": {reason: 0 for reason in ALL_REASONS},
        "valid_before_dedup": 0,
        "duplicates": 0,
        "final": 0,
    }


def process_source(scraper):
    """Scrape one source, then clean and validate its records.

    Returns (stats, valid_records). Records that fail never stop the run.
    """
    name = scraper.SOURCE_NAME
    result = scraper.scrape()

    stats = new_stats("completed" if result.completed else ("partial" if result.records else "failed"))
    stats["stop_reason"] = result.stop_reason
    stats["pages_fetched"] = result.pages_fetched
    stats["pages_failed"] = result.pages_failed
    stats["raw_collected"] = len(result.records) + result.record_errors
    stats["rejected_records"] = result.record_errors
    stats["rejected_by_reason"]["parse_error"] = result.record_errors
    stats.update(result.extras)  # e.g. detail_pages_fetched / detail_pages_failed

    valid = []
    for raw in result.records:
        try:
            record = clean_record(raw)
        except Exception as exc:
            stats["rejected_records"] += 1
            stats["rejected_by_reason"]["cleaning_error"] += 1
            logger.warning("[%s] Rejected record (cleaning_error): %s", name, exc)
            continue
        stats["cleaned"] += 1

        problems = validate_record(record)
        if problems:
            stats["rejected_records"] += 1
            for problem in problems:
                stats["rejected_by_reason"][problem] += 1
            label = (record.get("name_or_title") or "<no name>")[:60]
            logger.warning("[%s] Rejected record %r: %s", name, label, ", ".join(problems))
        else:
            valid.append(record)

    stats["valid_before_dedup"] = len(valid)
    return stats, valid


def write_csv(records, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)  # None becomes an empty cell


def write_summary(stats: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)  # create output/ if missing
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=4, ensure_ascii=False)


def run_pipeline(scrapers, output_dir: Path = OUTPUT_DIR) -> dict:
    """Run every stage in order and write both output files. Returns the summary dict."""
    started = datetime.now(timezone.utc)
    clock = time.perf_counter()

    per_source, valid_all = {}, []
    for scraper in scrapers:  # each source in its own try/except
        name = scraper.SOURCE_NAME
        try:
            stats, valid = process_source(scraper)
        except Exception as exc:
            logger.exception("[%s] Source failed unexpectedly: %s", name, exc)
            stats, valid = new_stats("failed"), []
            stats["stop_reason"] = f"unexpected error: {exc}"
        per_source[name] = stats
        valid_all.extend(valid)

    # Deduplicate across everything that survived validation.
    unique, dupes = find_duplicates(valid_all)
    for record in dupes:
        per_source[record["source"]]["duplicates"] += 1
        logger.warning("Duplicate removed: [%s] %r", record["source"], (record.get("name_or_title") or "")[:60])
    for name, stats in per_source.items():
        stats["final"] = stats["valid_before_dedup"] - stats["duplicates"]

    write_csv(unique, output_dir / "final_dataset.csv")

    ended = datetime.now(timezone.utc)
    reasons = Counter()
    for stats in per_source.values():
        reasons.update(stats["rejected_by_reason"])
    raw_total = sum(s["raw_collected"] for s in per_source.values())
    rejected_total = sum(s["rejected_records"] for s in per_source.values())

    summary = {
        "start_time": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(time.perf_counter() - clock, 1),
        "collected_per_source": {n: s["raw_collected"] for n, s in per_source.items()},
        "cleaned_per_source": {n: s["cleaned"] for n, s in per_source.items()},
        "rejected_per_source": {n: s["rejected_records"] for n, s in per_source.items()},
        # A record can fail several rules, so these reason counts can add up to more than
        # the number of rejected records.
        "rejected_by_reason": {reason: reasons[reason] for reason in ALL_REASONS},
        "duplicates_detected": len(dupes),
        "final_per_source": {n: s["final"] for n, s in per_source.items()},
        "final_record_count": len(unique),
        "reconciliation": {
            "raw_total": raw_total,
            "rejected_total": rejected_total,
            "duplicates_total": len(dupes),
            "final_total": len(unique),
            "balanced": raw_total - rejected_total - len(dupes) == len(unique),
        },
        "sources": per_source,
    }
    write_summary(summary, output_dir / "summary_report.json")
    if not summary["reconciliation"]["balanced"]:
        logger.error("Summary counts do not reconcile: %s", summary["reconciliation"])
    return summary


# --------------------------------------------------------------------------- main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Scrape Books to Scrape and Quotes to Scrape into one CSV.")
    parser.add_argument("--skip-details", action="store_true",
                        help="do not visit book detail pages (category/description stay empty; much faster)")
    parser.add_argument("--max-pages", type=int, default=None, metavar="N",
                        help="stop each site after N pages (for quick tests)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    configure_logging()
    logger.info("Run started")
    scrapers = [
        BooksScraper(fetch_details=not args.skip_details, max_pages=args.max_pages),
        QuotesScraper(max_pages=args.max_pages),
    ]
    summary = run_pipeline(scrapers)
    logger.info(
        "Run finished in %.1fs: final records=%d, rejected=%d, duplicates=%d, balanced=%s",
        summary["duration_seconds"], summary["final_record_count"],
        summary["reconciliation"]["rejected_total"], summary["duplicates_detected"],
        summary["reconciliation"]["balanced"],
    )
    return 0 if summary["final_record_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

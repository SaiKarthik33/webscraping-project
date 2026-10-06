"""End-to-end test of the pipeline stages with fake scrapers (no internet)."""
import csv
import json
import tempfile
from pathlib import Path

import main
from scrapers.base_scraper import ScrapeResult

SRC = "https://books.toscrape.com/catalogue/x/index.html"


def raw_book(title, price="\u00a310.00", rating="star-rating Three", url=SRC):
    return {"source": "Books to Scrape", "source_url": url, "title": title, "price_raw": price,
            "rating_raw": rating, "category_raw": "Poetry", "description_raw": "d", "scraped_at": "2026-01-01T00:00:00Z"}


def raw_quote(text, author="Oscar Wilde"):
    return {"source": "Quotes to Scrape", "source_url": "https://quotes.toscrape.com/", "text_raw": text,
            "author_raw": author, "tags_raw": ["life", "Be"], "scraped_at": "2026-01-01T00:00:00Z"}


class FakeScraper:
    def __init__(self, name, result=None, error=None):
        self.SOURCE_NAME, self.result, self.error = name, result, error

    def scrape(self):
        if self.error:
            raise self.error
        return self.result


def books_result():
    records = [
        raw_book("Good Book"),
        raw_book("GOOD  book"),  # duplicate (case/space)
        raw_book("Bad Price", price="\u00a3abc"),  # invalid_price
        raw_book(None),  # missing_name
        raw_book("Another Book", rating="star-rating Five"),
    ]
    return ScrapeResult(source="Books to Scrape", records=records, pages_fetched=2, record_errors=1)


def quotes_result():
    return ScrapeResult(source="Quotes to Scrape", pages_fetched=1,
                        records=[raw_quote("\u201cBe yourself.\u201d"), raw_quote("\u201cAnother one.\u201d")])


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_pipeline_counts_reconcile_and_files_are_written():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "output"  # does not exist yet: pipeline must create it
        summary = main.run_pipeline(
            [FakeScraper("Books to Scrape", books_result()), FakeScraper("Quotes to Scrape", quotes_result())], out)

        rows = read_csv(out / "final_dataset.csv")
        saved = json.loads((out / "summary_report.json").read_text(encoding="utf-8"))

    assert list(rows[0].keys()) == main.COLUMNS
    assert len(rows) == summary["final_record_count"] == saved["final_record_count"] == 4
    assert summary["collected_per_source"] == {"Books to Scrape": 6, "Quotes to Scrape": 2}
    assert summary["rejected_per_source"] == {"Books to Scrape": 3, "Quotes to Scrape": 0}
    reasons = summary["rejected_by_reason"]
    assert reasons["parse_error"] == 1 and reasons["invalid_price"] == 1 and reasons["missing_name"] == 1
    assert reasons["invalid_url"] == 0  # every known reason is present, even at zero
    assert summary["duplicates_detected"] == 1
    assert summary["reconciliation"] == {"raw_total": 8, "rejected_total": 3, "duplicates_total": 1,
                                         "final_total": 4, "balanced": True}
    assert {r["source"] for r in rows} == {"Books to Scrape", "Quotes to Scrape"}

    book_row = next(r for r in rows if r["name_or_title"] == "Good Book")
    assert book_row["price"] == "10.0" and book_row["rating"] == "3" and book_row["author"] == ""
    quote_row = next(r for r in rows if r["name_or_title"] == "Be yourself.")
    assert quote_row["price"] == "" and quote_row["tags"] == "be;life" and quote_row["author"] == "Oscar Wilde"


def test_one_source_crashing_does_not_stop_the_other():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        summary = main.run_pipeline(
            [FakeScraper("Books to Scrape", error=RuntimeError("site exploded")),
             FakeScraper("Quotes to Scrape", quotes_result())], out)
        rows = read_csv(out / "final_dataset.csv")

    assert summary["sources"]["Books to Scrape"]["status"] == "failed"
    assert summary["sources"]["Quotes to Scrape"]["status"] == "completed"
    assert len(rows) == 2 and {r["source"] for r in rows} == {"Quotes to Scrape"}
    assert summary["reconciliation"]["balanced"]

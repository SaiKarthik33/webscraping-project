from processing.cleaning import (
    clean_price, clean_rating, clean_record, clean_tags, clean_text,
    normalize_url, strip_quotes,
)


def test_clean_text_collapses_whitespace_and_nbsp():
    assert clean_text("  Hello \n World ") == "Hello World"
    assert clean_text("A\xa0\xa0B\tC") == "A B C"


def test_clean_text_empty_becomes_none():
    assert clean_text("   \n ") is None
    assert clean_text(None) is None


def test_strip_quotes_removes_curly_quotes():
    assert strip_quotes("\u201cThe world is round.\u201d") == "The world is round."
    assert strip_quotes("  \u201c Spaced   out \u201d ") == "Spaced out"
    assert strip_quotes(None) is None


def test_clean_price():
    assert clean_price("\u00a351.77") == 51.77
    assert clean_price("\u00c2\u00a351.77") == 51.77  # mis-decoded pound sign still parses
    assert clean_price("\u00a31,234.50") == 1234.50
    assert clean_price("free") is None
    assert clean_price(None) is None


def test_clean_rating():
    assert clean_rating("star-rating Three") == 3
    assert clean_rating("star-rating One") == 1
    assert clean_rating("star-rating FIVE") == 5
    assert clean_rating("4") == 4
    assert clean_rating("star-rating") is None
    assert clean_rating(None) is None


def test_clean_tags_lowercase_sort_dedupe_join():
    assert clean_tags(["Love", " life ", "LOVE", ""]) == "life;love"
    assert clean_tags([]) is None
    assert clean_tags(None) is None
    assert clean_tags("b; A") == "a;b"


def test_normalize_url():
    assert normalize_url(" https://a.com/x ") == "https://a.com/x"
    assert normalize_url("/page/2/", base="https://quotes.toscrape.com/") == "https://quotes.toscrape.com/page/2/"
    assert normalize_url("   ") is None


def test_clean_record_book():
    raw = {
        "source": "Books to Scrape", "source_url": "https://books.toscrape.com/catalogue/a_1/index.html",
        "title": "  A Light in the   Attic ", "price_raw": "\u00a351.77", "rating_raw": "star-rating Three",
        "category_raw": " Poetry ", "description_raw": "It's  hard\nto imagine.", "scraped_at": "2026-01-01T00:00:00Z",
    }
    rec = clean_record(raw)
    assert rec["name_or_title"] == "A Light in the Attic"
    assert rec["price"] == 51.77 and rec["rating"] == 3
    assert rec["category"] == "Poetry" and rec["description"] == "It's hard to imagine."
    assert rec["author"] is None and rec["tags"] is None


def test_clean_record_quote():
    raw = {
        "source": "Quotes to Scrape", "source_url": "https://quotes.toscrape.com/",
        "text_raw": "\u201cBe yourself.\u201d", "author_raw": " Oscar  Wilde ", "tags_raw": ["Life", "be"],
    }
    rec = clean_record(raw)
    assert rec["name_or_title"] == "Be yourself."
    assert rec["author"] == "Oscar Wilde" and rec["tags"] == "be;life"
    assert rec["price"] is None and rec["rating"] is None


def test_clean_record_keeps_unparseable_values_so_validation_can_reject_them():
    raw = {"source": "Books to Scrape", "source_url": "https://x.com", "title": "T",
           "price_raw": "\u00a3abc", "rating_raw": "star-rating"}
    rec = clean_record(raw)
    assert rec["price"] == "\u00a3abc" and rec["rating"] == "star-rating"

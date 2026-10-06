from processing.validation import validate_record


def good_book():
    return {"source": "Books to Scrape", "name_or_title": "A Book", "source_url": "https://books.toscrape.com/x",
            "price": 10.5, "rating": 4}


def test_valid_record_has_no_problems():
    assert validate_record(good_book()) == []


def test_valid_quote_without_price_and_rating():
    rec = {"source": "Quotes to Scrape", "name_or_title": "Hi", "source_url": "http://quotes.toscrape.com/",
           "price": None, "rating": None}
    assert validate_record(rec) == []


def test_unknown_source():
    rec = good_book(); rec["source"] = "Other Site"
    assert validate_record(rec) == ["unknown_source"]


def test_missing_name():
    rec = good_book(); rec["name_or_title"] = None
    assert validate_record(rec) == ["missing_name"]


def test_invalid_url():
    rec = good_book(); rec["source_url"] = "catalogue/page-2.html"
    assert validate_record(rec) == ["invalid_url"]
    rec["source_url"] = None
    assert validate_record(rec) == ["invalid_url"]


def test_invalid_price():
    for bad in (-1, "\u00a3abc", float("nan"), True):
        rec = good_book(); rec["price"] = bad
        assert validate_record(rec) == ["invalid_price"], bad
    rec = good_book(); rec["price"] = 0
    assert validate_record(rec) == []  # zero is allowed


def test_invalid_rating():
    for bad in (0, 6, "3", 2.5, "star-rating"):
        rec = good_book(); rec["rating"] = bad
        assert validate_record(rec) == ["invalid_rating"], bad


def test_multiple_problems_are_all_reported():
    rec = {"source": "Nope", "name_or_title": "", "source_url": "", "price": -5, "rating": 9}
    assert validate_record(rec) == [
        "unknown_source", "missing_name", "invalid_url", "invalid_price", "invalid_rating"]

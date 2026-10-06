from processing.deduplication import find_duplicates, make_fingerprint


def test_duplicates_ignore_case_and_spaces():
    base = {"source": "Books to Scrape", "author": None}
    records = [
        {**base, "name_or_title": "Example Book Title"},
        {**base, "name_or_title": "  Example Book Title "},
        {**base, "name_or_title": "EXAMPLE BOOK TITLE"},
    ]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 1 and len(dupes) == 2
    assert unique[0] is records[0]  # first occurrence is kept


def test_duplicates_ignore_punctuation():
    base = {"source": "Books to Scrape", "author": None}
    records = [{**base, "name_or_title": "It's a Book!"}, {**base, "name_or_title": "Its a book"}]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 1 and len(dupes) == 1


def test_quote_duplicates_use_author_and_first_50_characters():
    base = {"source": "Quotes to Scrape", "author": "Jane Austen"}
    long_text = "x" * 50
    records = [
        {**base, "name_or_title": long_text + " ending one"},
        {**base, "name_or_title": long_text.upper() + " a different ending"},  # same first 50 chars
        {**base, "author": "Someone Else", "name_or_title": long_text + " ending one"},  # other author
    ]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 2 and len(dupes) == 1


def test_same_title_in_different_sources_is_not_a_duplicate():
    a = {"source": "Books to Scrape", "author": None, "name_or_title": "Same"}
    b = {"source": "Quotes to Scrape", "author": None, "name_or_title": "Same"}
    assert make_fingerprint(a) != make_fingerprint(b)


def test_no_duplicates_in_clean_data():
    records = [{"source": "Books to Scrape", "author": None, "name_or_title": f"Book {i}"} for i in range(20)]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 20 and dupes == []

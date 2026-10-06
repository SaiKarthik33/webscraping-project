"""Names and column order shared by the processing modules."""

BOOKS_SOURCE = "Books to Scrape"
QUOTES_SOURCE = "Quotes to Scrape"
VALID_SOURCES = {BOOKS_SOURCE, QUOTES_SOURCE}

# Fixed column order of output/final_dataset.csv (one common data model).
COLUMNS = [
    "source",
    "source_url",
    "name_or_title",
    "category",
    "price",
    "rating",
    "author",
    "tags",
    "description",
    "scraped_at",
]

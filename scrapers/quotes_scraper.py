"""Quotes to Scrape: selectors and pagination start point."""
from scrapers.base_scraper import BaseScraper


class QuotesScraper(BaseScraper):
    SOURCE_NAME = "Quotes to Scrape"
    START_URL = "https://quotes.toscrape.com/"
    RECORD_SELECTOR = "div.quote"

    def parse_record(self, quote, page_url):
        text = quote.select_one("span.text")
        author = quote.select_one("small.author")
        author_link = quote.select_one('a[href^="/author/"]')
        return {
            # Documented choice: source_url = the listing page where the quote appeared.
            "source_url": page_url,
            "author_url": author_link.get("href") if author_link else None,
            "text_raw": text.get_text() if text else None,  # still wrapped in curly quotes
            "author_raw": author.get_text() if author else None,
            "tags_raw": [tag.get_text() for tag in quote.select("a.tag")],  # zero or more
        }

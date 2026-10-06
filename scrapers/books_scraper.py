"""Books to Scrape: selectors, pagination start point and detail-page enrichment."""
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class BooksScraper(BaseScraper):
    SOURCE_NAME = "Books to Scrape"
    START_URL = "https://books.toscrape.com/"
    RECORD_SELECTOR = "article.product_pod"

    def __init__(self, *args, fetch_details=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetch_details = fetch_details

    def parse_record(self, article, page_url):
        link = article.select_one("h3 > a")
        price = article.select_one("p.price_color")
        rating = article.select_one("p.star-rating")
        href = link.get("href") if link else None
        return {
            "title": link.get("title") if link else None,  # full title (visible text is cut off)
            "source_url": urljoin(page_url, href) if href else None,
            "price_raw": price.get_text() if price else None,
            # BeautifulSoup gives class as a list, e.g. ['star-rating', 'Three']
            "rating_raw": " ".join(rating.get("class", [])) if rating else None,
            "category_raw": None,  # filled from the detail page
            "description_raw": None,  # filled from the detail page
        }

    @staticmethod
    def parse_detail(soup):
        """Return (category, description) from a book detail page; None if missing."""
        crumbs = soup.select("ul.breadcrumb li a")  # Home > Books > <category>
        category = crumbs[2].get_text() if len(crumbs) >= 3 else None
        desc = soup.select_one("#product_description + p")
        return category, (desc.get_text() if desc else None)

    def after_scrape(self, result):
        """Visit each book's detail page for category and description.

        A failed detail page is logged and skipped: the book keeps empty
        category/description instead of being dropped.
        """
        ok = failed = 0
        if not self.fetch_details:
            logger.info("[%s] Detail pages skipped (category/description left empty)", self.SOURCE_NAME)
        else:
            total = len(result.records)
            logger.info("[%s] Fetching %d detail pages", self.SOURCE_NAME, total)
            for index, record in enumerate(result.records, start=1):
                url = record.get("source_url")
                if not url:
                    continue
                try:
                    soup = BeautifulSoup(self.fetch(url).text, "lxml")
                    record["category_raw"], record["description_raw"] = self.parse_detail(soup)
                    ok += 1
                except requests.RequestException as exc:
                    failed += 1
                    logger.error("[%s] Failed to fetch detail page %s: %s", self.SOURCE_NAME, url, exc)
                except Exception as exc:
                    failed += 1
                    logger.warning("[%s] Could not parse detail page %s: %s", self.SOURCE_NAME, url, exc)
                if index % 100 == 0:
                    logger.info("[%s] Detail pages: %d/%d", self.SOURCE_NAME, index, total)
        result.extras["detail_pages_fetched"] = ok
        result.extras["detail_pages_failed"] = failed

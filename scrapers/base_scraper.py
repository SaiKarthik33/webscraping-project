"""Shared networking and pagination for every scraper.

Holds the HTTP session (User-Agent, retries), the timeout, the polite delay
between requests, and the "follow the next link until there is none" loop.
Site-specific scrapers only supply selectors and a record parser.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

USER_AGENT = "ScrapingAssignment/1.0 (learning project)"
REQUEST_TIMEOUT = 10  # seconds
REQUEST_DELAY = 0.5  # seconds between requests
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]


def create_session() -> requests.Session:
    """One session that retries temporary failures with growing delays."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retries = Retry(total=3, backoff_factor=1.0, status_forcelist=RETRY_STATUS_CODES)
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ScrapeResult:
    """Everything one scraper run produced, including how it went."""

    source: str
    records: list = field(default_factory=list)
    pages_fetched: int = 0
    pages_failed: int = 0
    record_errors: int = 0  # records found on a page but not parseable
    completed: bool = True  # False if the run stopped early
    stop_reason: str = ""
    extras: dict = field(default_factory=dict)


class BaseScraper:
    SOURCE_NAME = ""
    START_URL = ""
    RECORD_SELECTOR = ""
    NEXT_SELECTOR = "li.next > a"

    def __init__(self, session=None, delay=REQUEST_DELAY, timeout=REQUEST_TIMEOUT, max_pages=None):
        self.session = session or create_session()
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages

    # ---- networking -------------------------------------------------------
    def fetch(self, url):
        """GET one URL. Raises requests.RequestException on any failure."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            logger.debug("GET %s -> HTTP %s", url, response.status_code)
            response.raise_for_status()  # raises on 404, 500, ...
            response.encoding = "utf-8"  # keeps the £ symbol correct
            return response
        finally:
            time.sleep(self.delay)  # be polite to the server

    # ---- to be provided by each site -----------------------------------------
    def parse_record(self, element, page_url):
        """Return a raw dict (text exactly as found) for one record element."""
        raise NotImplementedError

    def after_scrape(self, result):
        """Optional hook, e.g. fetch detail pages. Must not raise."""

    # ---- pagination ---------------------------------------------------------------
    def scrape(self) -> ScrapeResult:
        result = ScrapeResult(source=self.SOURCE_NAME)
        url, page, visited = self.START_URL, 1, set()
        logger.info("[%s] Starting at %s", self.SOURCE_NAME, url)

        while url:
            if self.max_pages is not None and page > self.max_pages:
                result.completed, result.stop_reason = False, f"max_pages={self.max_pages} reached"
                logger.info("[%s] %s; stopping", self.SOURCE_NAME, result.stop_reason)
                break
            if url in visited:  # protects against a "next" link that loops
                result.completed, result.stop_reason = False, f"pagination loop at {url}"
                logger.warning("[%s] %s; stopping", self.SOURCE_NAME, result.stop_reason)
                break
            visited.add(url)

            logger.info("[%s] Page %d: %s", self.SOURCE_NAME, page, url)
            try:
                response = self.fetch(url)
            except requests.RequestException as exc:
                logger.error("[%s] Failed to fetch %s: %s", self.SOURCE_NAME, url, exc)
                result.pages_failed += 1
                result.completed, result.stop_reason = False, f"page failed: {url}"
                break  # stop THIS source; the other source still runs
            result.pages_fetched += 1

            try:
                soup = BeautifulSoup(response.text, "lxml")
                self._parse_page(soup, url, result)
                next_link = soup.select_one(self.NEXT_SELECTOR)
                href = next_link.get("href") if next_link else None
                url = urljoin(url, href) if href else None
            except Exception as exc:  # unexpected page-level problem
                logger.exception("[%s] Could not process %s: %s", self.SOURCE_NAME, url, exc)
                result.completed, result.stop_reason = False, f"page processing error: {url}"
                break
            page += 1

        self.after_scrape(result)
        logger.info(
            "[%s] Finished: %d pages, %d records, %d unparseable records, completed=%s",
            self.SOURCE_NAME, result.pages_fetched, len(result.records),
            result.record_errors, result.completed,
        )
        return result

    def _parse_page(self, soup, page_url, result):
        elements = soup.select(self.RECORD_SELECTOR)
        if not elements:
            logger.warning("[%s] No records found on %s", self.SOURCE_NAME, page_url)
        for element in elements:
            try:  # one bad record is logged and skipped
                record = self.parse_record(element, page_url)
                record["source"] = self.SOURCE_NAME
                record["scraped_at"] = utc_now_iso()
                result.records.append(record)
            except Exception as exc:
                result.record_errors += 1
                logger.warning("[%s] Skipping unparseable record on %s: %s",
                               self.SOURCE_NAME, page_url, exc)

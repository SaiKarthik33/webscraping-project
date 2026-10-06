"""Scraper tests with a fake HTTP session: no internet needed."""
import requests

from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

BOOKS_HOME = "https://books.toscrape.com/"
BOOKS_P2 = "https://books.toscrape.com/catalogue/page-2.html"
QUOTES_HOME = "https://quotes.toscrape.com/"


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code, self.encoding = text, status, None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, pages):
        self.pages, self.requested = pages, []

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url not in self.pages:
            raise requests.ConnectionError(f"no route to {url}")
        status, html = self.pages[url]
        return FakeResponse(html, status)


def book(title, href, price="\u00a310.00", rating="Three"):
    return (
        f'<article class="product_pod"><h3><a href="{href}" title="{title}">{title[:10]}...</a></h3>'
        f'<div class="product_price"><p class="price_color">{price}</p></div>'
        f'<p class="star-rating {rating}"></p></article>'
    )


def listing(articles, next_href=None):
    nxt = f'<li class="next"><a href="{next_href}">next</a></li>' if next_href else ""
    return f"<html><body>{''.join(articles)}<ul class='pager'>{nxt}</ul></body></html>"


def detail(category, description):
    return (
        '<html><body><ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="/b">Books</a></li>'
        f'<li><a href="/c">{category}</a></li><li class="active">x</li></ul>'
        f'<div id="product_description" class="sub-header"><h2>Product Description</h2></div><p>{description}</p>'
        "</body></html>"
    )


def quote(text, author, tags):
    links = "".join(f'<a class="tag" href="/tag/{t}/page/1/">{t}</a>' for t in tags)
    return (
        f'<div class="quote"><span class="text">\u201c{text}\u201d</span>'
        f'<span>by <small class="author">{author}</small><a href="/author/{author.replace(" ", "-")}">(about)</a></span>'
        f'<div class="tags">Tags: {links}</div></div>'
    )


def two_page_books_site():
    return {
        BOOKS_HOME: (200, listing([book("Book One Title", "catalogue/b1_1/index.html"),
                                   book("Book Two Title", "catalogue/b2_2/index.html", rating="Five")],
                                  next_href="catalogue/page-2.html")),
        BOOKS_P2: (200, listing([book("Book Three Title", "b3_3/index.html")])),  # no next link: last page
        "https://books.toscrape.com/catalogue/b1_1/index.html": (200, detail("Poetry", "Desc one")),
        "https://books.toscrape.com/catalogue/b2_2/index.html": (200, detail("Travel", "Desc two")),
        "https://books.toscrape.com/catalogue/b3_3/index.html": (200, detail("Fiction", "Desc three")),
    }


def test_books_follow_next_link_until_none_and_read_detail_pages():
    session = FakeSession(two_page_books_site())
    result = BooksScraper(session=session, delay=0).scrape()
    assert result.completed and result.pages_fetched == 2 and result.pages_failed == 0
    assert [r["title"] for r in result.records] == ["Book One Title", "Book Two Title", "Book Three Title"]
    first = result.records[0]
    assert first["source"] == "Books to Scrape"
    assert first["source_url"] == "https://books.toscrape.com/catalogue/b1_1/index.html"
    assert first["price_raw"] == "\u00a310.00" and first["rating_raw"] == "star-rating Three"
    assert first["category_raw"] == "Poetry" and first["description_raw"] == "Desc one"
    assert result.records[2]["source_url"] == "https://books.toscrape.com/catalogue/b3_3/index.html"
    assert first["scraped_at"].endswith("Z")
    assert session.requested[:2] == [BOOKS_HOME, BOOKS_P2]
    assert result.extras == {"detail_pages_fetched": 3, "detail_pages_failed": 0}


def test_books_without_details_makes_no_detail_requests():
    session = FakeSession(two_page_books_site())
    result = BooksScraper(session=session, delay=0, fetch_details=False).scrape()
    assert len(result.records) == 3 and len(session.requested) == 2
    assert result.records[0]["category_raw"] is None and result.records[0]["description_raw"] is None


def test_failed_page_stops_this_source_but_keeps_earlier_records():
    pages = two_page_books_site()
    pages[BOOKS_P2] = (503, "")
    result = BooksScraper(session=FakeSession(pages), delay=0, fetch_details=False).scrape()
    assert len(result.records) == 2
    assert result.pages_fetched == 1 and result.pages_failed == 1 and not result.completed


def test_failed_detail_page_keeps_the_book():
    pages = two_page_books_site()
    del pages["https://books.toscrape.com/catalogue/b2_2/index.html"]
    result = BooksScraper(session=FakeSession(pages), delay=0).scrape()
    assert len(result.records) == 3
    assert result.records[1]["category_raw"] is None
    assert result.extras == {"detail_pages_fetched": 2, "detail_pages_failed": 1}


def test_bad_record_is_skipped_and_counted():
    class Flaky(BooksScraper):
        def parse_record(self, article, page_url):
            if "Two" in article.select_one("h3 > a").get("title"):
                raise ValueError("boom")
            return super().parse_record(article, page_url)

    result = Flaky(session=FakeSession(two_page_books_site()), delay=0, fetch_details=False).scrape()
    assert len(result.records) == 2 and result.record_errors == 1 and result.completed


def test_missing_elements_give_none_instead_of_crashing():
    html = listing(['<article class="product_pod"><h3></h3></article>'])
    result = BooksScraper(session=FakeSession({BOOKS_HOME: (200, html)}), delay=0, fetch_details=False).scrape()
    rec = result.records[0]
    assert rec["title"] is None and rec["source_url"] is None
    assert rec["price_raw"] is None and rec["rating_raw"] is None


def test_pagination_loop_is_detected():
    html = listing([book("Only", "catalogue/o_1/index.html")], next_href="/")  # points back to the page itself
    result = BooksScraper(session=FakeSession({BOOKS_HOME: (200, html)}), delay=0, fetch_details=False).scrape()
    assert result.pages_fetched == 1 and not result.completed and "loop" in result.stop_reason


def test_max_pages_limit():
    result = BooksScraper(session=FakeSession(two_page_books_site()), delay=0,
                          fetch_details=False, max_pages=1).scrape()
    assert result.pages_fetched == 1 and len(result.records) == 2 and not result.completed


def test_quotes_parse_and_paginate():
    pages = {
        QUOTES_HOME: (200, "<html>" + quote("Be yourself.", "Oscar Wilde", ["life", "be"])
                      + quote("No tags here.", "Jane Austen", [])
                      + '<li class="next"><a href="/page/2/">Next</a></li></html>'),
        QUOTES_HOME + "page/2/": (200, "<html>" + quote("Second page.", "Mark Twain", ["wit"]) + "</html>"),
    }
    session = FakeSession(pages)
    result = QuotesScraper(session=session, delay=0).scrape()
    assert result.completed and result.pages_fetched == 2 and len(result.records) == 3
    first = result.records[0]
    assert first["source"] == "Quotes to Scrape" and first["source_url"] == QUOTES_HOME
    assert first["text_raw"] == "\u201cBe yourself.\u201d" and first["author_raw"] == "Oscar Wilde"
    assert first["tags_raw"] == ["life", "be"] and first["author_url"] == "/author/Oscar-Wilde"
    assert result.records[1]["tags_raw"] == []
    assert result.records[2]["source_url"] == QUOTES_HOME + "page/2/"

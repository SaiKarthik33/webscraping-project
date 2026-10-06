# Web Data Pipeline: Books to Scrape + Quotes to Scrape

A small ETL pipeline. One command (`python main.py`) scrapes both practice sites, cleans and
validates every record, removes duplicates, and writes one tidy CSV, a JSON summary and a log.

```
Scrape (both sites) -> Clean -> Validate -> Deduplicate -> Consolidate -> Save files
```

## Python version
Developed and tested on Python 3.12 (works on 3.10 - 3.12). Libraries: `requests`, `beautifulsoup4`, `lxml`
(+ `pytest` for tests). Everything else is the standard library.

## Setup
```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## How to run
```bash
python main.py                      # full run: ~1,000 books incl. detail pages + 100 quotes
python main.py --skip-details       # much faster: books keep empty category/description
python main.py --max-pages 2        # quick smoke test (2 pages per site)
python -m pytest                    # unit tests, no internet needed
```
A full run visits 50 listing pages + ~1,000 book detail pages + 10 quote pages with a 0.5 s pause after every
request, so expect roughly 10-20 minutes depending on the network. Outputs:

| File | Content |
|---|---|
| `output/final_dataset.csv` | one row per unique, valid record, same columns for every row |
| `output/summary_report.json` | counts per source, rejection reasons, duplicates, final total, run time |
| `logs/scraper.log` | time-stamped log of every request (DEBUG), page (INFO), rejection/duplicate (WARNING), failure (ERROR). Overwritten on each run |

## Website inspection (Stage 1)
| Item | Books to Scrape | Quotes to Scrape |
|---|---|---|
| One record | `article.product_pod` | `div.quote` |
| Main text | `h3 > a`, full title in the `title` attribute (visible text is cut off with `...`) | `span.text` (wrapped in curly quotes) |
| Price | `p.price_color` (e.g. `£51.77`) | none |
| Rating | class on `p.star-rating` (e.g. `Three`) | none |
| Author | none | `small.author` |
| Tags | none | `a.tag` (zero or more) |
| Link | `h3 > a[href]` (relative path) | `a[href^="/author/"]` (author page) |
| Next page | `li.next > a` | `li.next > a` |
| Detail page (Books) | category = 3rd breadcrumb link (`ul.breadcrumb li a`); description = `#product_description + p` | n/a |

Both sites are plain server-rendered HTML, so Requests + BeautifulSoup is enough; a browser tool such as
Selenium would only add overhead.

## Project layout
```
scrapers/    base_scraper.py (session, retries, timeout, delay, pagination loop)
             books_scraper.py / quotes_scraper.py (selectors + record parsing only)
processing/  cleaning.py, validation.py, deduplication.py, constants.py (source names, column order)
tests/       unit tests (cleaning, validation, deduplication, scrapers with a fake session, pipeline)
main.py      connects the stages, configures logging, writes the files
```
Rule of thumb: touches the internet -> `scrapers/`; only transforms data -> `processing/`; connects stages -> `main.py`.

## How pagination works
`BaseScraper.scrape()` starts at the home page, downloads and parses it, collects every record, then looks for
`li.next > a`. If it exists, its relative `href` is turned into a full URL with `urljoin` and the loop repeats;
if not, the source is finished. No page numbers are hard-coded, so the scraper keeps working if the site gains or
loses pages. Safeguards: a visited-URL set stops an endless "next" loop, and `--max-pages` caps a test run.

## Data model (one common table)
| Column | Books | Quotes |
|---|---|---|
| `source` | Books to Scrape | Quotes to Scrape |
| `source_url` | book detail page URL | **listing page URL where the quote appeared** (documented choice) |
| `name_or_title` | book title | quote text (curly quotes removed) |
| `category` | from detail page, else empty | empty |
| `price` | number, e.g. `51.77` (GBP, currency symbol dropped) | empty |
| `rating` | integer 1-5 | empty |
| `author` | empty | author name |
| `tags` | empty | `tag1;tag2` (lowercase, sorted, de-duplicated) |
| `description` | from detail page, else empty | empty |
| `scraped_at` | UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` | UTC timestamp |

Fields that do not apply stay empty; no fake values (e.g. a price of 0 for quotes) are invented.

## Cleaning (`processing/cleaning.py`)
Pure functions, testable with plain strings: `clean_text` (collapses spaces, tabs, newlines, `\xa0`; empty -> None),
`strip_quotes`, `clean_price` (`£51.77` -> `51.77`), `clean_rating` (`Three` -> `3`), `clean_tags`, `normalize_url`,
and `clean_record` which maps one raw scraped dict onto the common model. Pages are decoded as UTF-8
(`response.encoding = "utf-8"`) so `£` never turns into `Â£`.
If a price/rating is present but cannot be parsed, the raw text is kept so validation rejects the record with a
clear reason instead of silently producing an empty cell.

## Validation (`processing/validation.py`)
`validate_record` returns a list of problems (empty list = valid): `unknown_source`, `missing_name`, `invalid_url`
(must start with http:// or https://), `invalid_price` (present but not a number >= 0), `invalid_rating` (present
but not an integer 1-5). Rejected records are logged as WARNING, counted per reason in the summary, and the run
continues. Two extra pipeline-level reasons exist: `parse_error` (a record element could not be parsed on the page)
and `cleaning_error` (cleaning raised an exception).

## Duplicate detection (`processing/deduplication.py`)
A fingerprint (SHA-256) is built from the identifying fields after lowercasing, removing punctuation and collapsing
spaces:
- Books: `source + title`
- Quotes: `source + author + first 50 characters of the quote text`

A `set` of seen fingerprints decides if a record is a duplicate. **The first occurrence is kept and later ones are
removed** (not flagged), because the assignment wants one row per unique record; every removal is logged as a
WARNING and counted in the summary. The 50-character cut is applied *after* normalisation so spacing or punctuation
differences cannot hide a duplicate. The live sites contain no duplicates, so the logic is proven by unit tests with
deliberately duplicated records (`tests/test_deduplication.py`).

## Error handling
- `requests.Session` with a User-Agent, a 10 s timeout and automatic retries (3x, growing delay) for HTTP 429/500/502/503/504.
- If a page still fails after retries: ERROR is logged and **that source stops** (records collected so far are kept,
  status = `partial`). The other source still runs. Each source is also wrapped in its own `try/except` in `main.py`.
- Each record is parsed in its own `try/except`; one bad record is logged and counted, not fatal.
- Missing HTML elements give `None` (checked before use), never a crash.
- A failed book detail page is logged and the book is kept with empty category/description.

## Summary report
`summary_report.json` contains, per source and overall: raw records collected, records after cleaning, rejected
records and counts per reason, duplicates, final count, start/end time and duration. The numbers reconcile:
`raw - rejected - duplicates = final` (see the `reconciliation` block, `balanced: true`). "Raw" means record
elements found on pages, including any that could not be parsed. A record can fail more than one rule, so the sum
of the per-reason counts can exceed the number of rejected records.

## Assumptions
- Both sites keep their current HTML structure and the `li.next > a` pagination.
- Prices are in GBP; only the number is stored.
- For quotes, `source_url` is the listing page, so it is not unique per quote (identity comes from author + text).
- The CSV is UTF-8 without BOM; when opening in Excel use *Data > From Text/CSV* with UTF-8.

## Known limitations
- Fetching ~1,000 detail pages dominates the run time (use `--skip-details` for a quick run).
- A page that fails after retries ends that source early (partial data, clearly reported) rather than skipping ahead.
- Quote duplicates are matched on author + first 50 normalised characters, so two different quotes by the same
  author with an identical 50-character start would be treated as duplicates.
- No concurrency, by design (polite scraping, simple code).

## Results of my run
_TODO after running `python main.py`: paste the real numbers from `output/summary_report.json` here
(collected / rejected / duplicates / final / duration)._

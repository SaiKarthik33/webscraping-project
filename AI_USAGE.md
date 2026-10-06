# AI Usage

> the assignment asks for an honest record, and you must be able to explain every line in the interview.

## Tools used
- **Claude (Anthropic), chat on claude.ai**: I used Claude mainly for a small amount of code review and implementation
guidance.
The main areas were:
- Reviewing whether the implementation was sufficiently dynamic.
- Checking general Python coding practices and maintainability.
- Getting suggestions for improving the existing implementation.
- Reviewing edge cases that could affect the scraper and pipeline.
- Checking whether the implementation aligned with the assignment requirements.

## A real prompt I used
> "Check the code and follow the best coding practices, check if the code is fully dynamic and give me the suggestions to improve the code further"

After receiving suggestions, I reviewed them against the assignment
requirements and the existing implementation.
The final implementation follows the ETL flow:
Scrape -> Clean -> Validate -> Deduplicate -> Consolidate -> Save
The project also separates the scraping layer from the processing layer, with
main.py connecting the stages.
I specifically reviewed the following areas:
1. Dynamic pagination
The scraper follows the li.next > a link instead of relying on a hard-coded
page count. A visited-URL safeguard is also used to prevent an accidental
pagination loop.
2. Error handling
HTTP requests use a session with timeout and retry handling. A failure in one
source does not prevent the other source from running, and individual record
parsing errors do not terminate the complete run.
3. Data cleaning
Text, prices, ratings, tags, and URLs are normalized before validation.
Unparseable values can be retained so validation can reject them with an
explicit reason rather than silently losing the problem.
4. Validation
Records are checked for valid source, required name/title, URL, price, and
rating. Rejection reasons are included in the summary.
5. Duplicate detection
Records are fingerprinted after normalizing case, punctuation, and whitespace.
The first occurrence is retained and later duplicates are removed.
6. Pipeline accounting
The summary report checks that raw records, rejected records, duplicates, and
final records reconcile.

## Mistakes found while reviewing / testing
- A first version of the pagination-loop test passed for the wrong reason (the fake "next" URL was simply missing from the fake site, so it failed to fetch instead of detecting a loop). Fixed by pointing the link back at the page itself and asserting the stop reason.
- `requests.Session` has no default timeout, so the timeout is applied in `BaseScraper.fetch` on every call.
- [Add anything YOU found, e.g. selector or encoding problems on the live sites.]

## How the final code was tested
- Unit tests for cleaning, validation, deduplication (including deliberately duplicated records).
- Scraper tests with a fake HTTP session: pagination, failed page, failed detail page, bad record, missing elements, loop guard.
- Pipeline tests: counts reconcile, files written, one source crashing does not stop the other.
- An end-to-end run of the real `requests` session + `lxml` against a local mock server (including a transient 503 that the retry recovered from).
- [Your own checks: fresh venv + `pip install -r requirements.txt` + `python main.py` on the live sites; compare JSON counts with CSV row count; open the CSV and check prices are numbers and ratings are 1-5.]

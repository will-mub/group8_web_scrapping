# DSC2107 Data Mining & Wrangling — Group 8
Group members
• John baker Hall Kasujja
• Mubbale Wilson
• Nankunda Rowena
• Namugga Daniella
• Cherissa Iteriteka 
• Apio Lewis

This project contains the Day 1 warm-up and a daily scraper for the assigned itch.io Top Sellers page.

## Important assignment requirements

- Group 8 target: `https://itch.io/games/top-sellers`
- Fields: rank, title, developer, price, genre, platforms
- At least 500 ranked items per daily run, with a scrape timestamp
- Seven consecutive daily runs
- Keep raw daily CSV/JSON unchanged; clean separately and store in SQLite
- Respect `robots.txt`, wait 2–5 seconds between requests, use a course-identifying User-Agent, and stop if blocked

## 1. Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Warm-up: pagination and detail pages

```bash
python warmup_books.py
```

The warm-up visits each listing page, follows the `Next` link (pagination), collects each book card, opens each book's detail page, extracts extra fields from its product-information table, and saves `data/raw/books_warmup.csv`.

The warm-up makes many requests. Run it only as coursework practice and keep the required 2–5 second delay. If you encounter a block or error, stop and document it.

## 3. Run Group 8 once

Edit `USER_AGENT` in `scraper.py` and replace the placeholder with your course contact email, then run:

```bash
python scraper.py
```

At run start, the scraper checks `https://itch.io/robots.txt`. It scrapes only public top-seller listing pages. It assigns rank based on order in the sorted results and collects visible card fields. It does not visit individual game pages by default because the required fields are generally represented on the listing card; missing fields remain blank instead of being invented.

Outputs:

- `data/raw/itchio_top_sellers_YYYY-MM-DD.csv` — raw evidence
- `data/raw/itchio_top_sellers_YYYY-MM-DD.json` — raw evidence
- `data/cleaned/itchio_top_sellers_cleaned_YYYY-MM-DD.csv` — cleaned values
- `data/group8_itchio.sqlite` — `products` and `observations` tables
- `logs/scraper.log` — progress, warnings, and errors

The scraper may collect fewer than 500 if the site changes its HTML, the server blocks the request, or pagination stops unexpectedly. Inspect the log and document the limitation rather than bypassing protections.

## 4. Enable daily automation with GitHub Actions

1. Create a private GitHub repository for the group and upload these files.
2. In **Settings → Secrets and variables → Actions → Variables**, create a variable named `STUDENT_EMAIL` with the contact email required by your course.
3. In **Settings → Actions → General → Workflow permissions**, allow read and write permissions if your repository policy permits it.
4. Open the **Actions** tab and enable workflows if GitHub asks.
5. Run **Daily itch.io Group 8 collection → Run workflow** once to test.
6. The workflow is scheduled for 06:30 UTC (09:30 Uganda time) daily. Monitor each run in Actions and verify the new CSV/JSON and SQLite database are committed.
7. The assignment requires seven consecutive daily runs; after the seventh successful run, disable the workflow to prevent unnecessary future collection.

GitHub may delay scheduled workflows. Do not rely on cron as an exact-time guarantee. Never enable automation until you have checked the site's current robots.txt and terms. If you receive HTTP 403 or 429, stop and document it; do not bypass it.

## 5. Analysis ideas

Use the seven observations to investigate rank movement, price distribution, genres/platforms represented in the top sellers, and daily changes. Be cautious: a missing price is not automatically a numeric zero, and the site's top-seller ordering is a platform ranking rather than an exact published sales count.

## Troubleshooting

- **No cards found:** inspect the current page HTML and update CSS selectors only after documenting the change.
- **Fewer than 500 records:** inspect pagination, logs, and any redirects. Do not increase request rates to compensate.
- **403/429:** stop; document the block and follow the assignment rules.
- **GitHub push rejected:** check repository Actions write permissions and branch protection rules.

"""DSC2107 Group 8: responsible itch.io Top Sellers scraper.
"""
PROJECT: WEB SCRAPER FOR GAME LISTINGS

PURPOSE:
To collect information about games listed on itch.io
and prepare the information for data analysis.

HOW THE PROGRAM WORKS:
1. Connects to the website and requests pages.
2. Finds game listings and extracts their details.
3. Removes duplicate game records.
4. Saves the original data in CSV and JSON formats.
5. Cleans price information.
6. Saves the cleaned data and records in an SQLite database.

EXPECTED RESULT:
A collection of game records that can be examined and
used for further data analysis.

NOTE:
The number of records collected depends on the available
listings and whether the scraping process completes successfully.
"""
The script collects public listing-card fields only. It does not log in, visit"
search/checkout/download routes, bypass blocks, or use proxies to evade limits.
Run locally with: python scraper.py
"""
# IMPORTING LIBRARIES
# These libraries provide the tools needed for our web scraper.
# They help us download web pages, extract information,
# clean data, save files, and store information in a database.

from __future__ import annotations

import csv
import json
import logging
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlencode
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

# PROJECT CONFIGURATION
# This section contains the main settings for the scraper.
# It specifies the website to visit, the number of records
# we want to collect, request limits, and delays between requests.
BASE_URL = "https://itch.io/games/top-sellers"
ROBOTS_URL = "https://itch.io/robots.txt"
USER_AGENT = "DSC2107-Group8-Course-Project (wmubs4@gmail.com)"
# Limits and delays
TARGET_COUNT = 500                         # Assignment asks for top 500 items.
MAX_REQUESTS_PER_RUN = 1000                # Assignment's approximate daily cap.
MIN_DELAY_SECONDS = 2.0                    # Assignment requires 2–5 seconds.
MAX_DELAY_SECONDS = 5.0
MAX_RETRIES = 3
# File and folder paths
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "cleaned"
DB_PATH = ROOT / "data" / "group8_itchio.sqlite"
LOG_PATH = ROOT / "logs" / "scraper.log"

# LOGGING AND SESSION SETUP
# Logging records what the program is doing and helps us
# identify errors. The session manages our website requests
# and allows us to reuse connection settings.
# Log progress and failures to both the terminal and a file for the report.
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_PATH, encoding="utf-8")],
)

# HTTP session

# A session reuses the connection. A clear User-Agent identifies the project.
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
# Tracking request
request_count = 0
last_request_at = 0.0

# REQUEST DELAYS AND WEBSITE RULES
# The delay helps prevent requests from being sent too quickly.
# Website access rules are checked to help determine whether
# the scraper is allowed to access the requested pages.

#control of the delay between HTTP requests 
def wait_between_requests() -> None:
    """Wait 2–5 seconds between requests, including requests to detail pages."""
    global last_request_at
    if last_request_at:
        required_delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        elapsed = time.monotonic() - last_request_at
        if elapsed < required_delay:
            time.sleep(required_delay - elapsed)

# Check the sites crawler instructions 
def check_robots() -> RobotFileParser:
    """Read robots.txt and stop if the target listing route is disallowed."""
    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    # robots.txt itself is fetched once; if this fails, do not assume permission.
    wait_between_requests()
    response = session.get(ROBOTS_URL, timeout=20)
    global request_count, last_request_at
    request_count += 1
    last_request_at = time.monotonic()
    response.raise_for_status()
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(USER_AGENT, BASE_URL):
        raise RuntimeError(f"robots.txt disallows scraping {BASE_URL}; stopping.")
    logging.info("robots.txt checked: target listing URL is allowed for this User-Agent.")
    return parser

# WEB PAGE REQUEST HANDLING
# This function requests a web page and checks whether the
# request is allowed. It handles connection errors and retries
# failed requests when appropriate, then returns the page
# content for further processing.
def get_page(url: str) -> BeautifulSoup:
    """Fetch and parse one permitted HTML page with retries and back-off."""
    global request_count, last_request_at
    # Fail closed if the run would exceed the coursework request limit.
    if request_count >= MAX_REQUESTS_PER_RUN:
        raise RuntimeError("Request cap reached; stopping rather than exceeding the limit.")

    # Never fetch a route robots.txt disallows.
    parsed_url = urlparse(url)
    if parsed_url.netloc not in {"itch.io", "www.itch.io"}:
        raise ValueError(f"Unexpected host refused: {parsed_url.netloc}")
    # Re-check robots permission for every requested URL.
    robots = RobotFileParser()
    robots.set_url(ROBOTS_URL)
    # robots content was checked at run start; load cached rules from the local copy.
    robots.parse(ROBOTS_LINES)
    if not robots.can_fetch(USER_AGENT, url):
        raise RuntimeError(f"robots.txt disallows URL: {url}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        wait_between_requests()
        try:
            response = session.get(url, timeout=25)
            request_count += 1
            last_request_at = time.monotonic()
            # A block or forbidden response is a signal to stop, not bypass.
            if response.status_code in (401, 403, 429):
                raise RuntimeError(
                    f"Server returned HTTP {response.status_code}. Stop and document the block; do not bypass it."
                )
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except RuntimeError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            logging.warning("Request attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                # Exponential back-off after errors; still obeys the minimum wait rule.
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")

# TEXT CLEANING
# This function removes unnecessary spaces and formats text
# so that the collected information is easier to read and use.
def clean_text(node) -> str | None:
    """Return readable text from an HTML element, or None for a missing field."""
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None

# GAME INFORMATION EXTRACTION
# This function reads one game listing and extracts its details,
# such as the title, developer, price, genre, platforms, and URL.
# The extracted details are organized into a dictionary.
def parse_game_card(card, rank: int, listing_url: str, scraped_at: str) -> dict:
    """Extract the assignment fields from one game card in the listing page."""
    # Title links are commonly marked .title; use fallbacks if the layout changes.
    title_link = card.select_one("a.title") or card.select_one(".game_title a") or card.select_one("a[href]")
    title = clean_text(title_link)
    game_url = urljoin(listing_url, title_link.get("href", "")) if title_link else None

    # The author/developer is shown on the public listing card.
    author_node = card.select_one(".game_author a") or card.select_one("a.game_author") or card.select_one(".author a")
    developer = clean_text(author_node)

    # Price may be absent for free games. Preserve the displayed wording as raw data.
    price_node = card.select_one(".price_value") or card.select_one(".game_price") or card.select_one(".price")
    price = clean_text(price_node)
    if not price:
        # Distinguish a genuinely missing displayed price from a guessed numeric price.
        price = "Free / no price displayed" if card.select_one(".game_price, .price_value, .price") is None else None

    # Genre and platform labels vary slightly across cards; collect visible text.
    genre_node = card.select_one(".game_genre") or card.select_one(".genre")
    genre = clean_text(genre_node)
    platform_nodes = card.select(".game_platform, .game_platforms, .platforms, [class*='platform']")
    platform_values = []
    for node in platform_nodes:
        value = clean_text(node)
        if value and value not in platform_values:
            platform_values.append(value)
        # Some platform icons store the label in a title or aria-label attribute.
        for attr in ("title", "aria-label"):
            label = node.get(attr)
            if label and label not in platform_values:
                platform_values.append(label.strip())
    platforms = "; ".join(platform_values) if platform_values else None

    # Rank is the item's position in the ordered top-sellers listing, not a claim
    # that itch.io prints a numeric rank beside every card.
    return {
        "rank": rank,
        "title": title,
        "developer": developer,
        "price": price,
        "genre": genre,
        "platforms": platforms,
        "game_url": game_url,
        "listing_page": listing_url,
        "scraped_at": scraped_at,
    }


def find_cards(soup: BeautifulSoup):
    """Find listing cards; several selectors are tried to tolerate minor HTML changes."""
    cards = soup.select(".game_cell")
    if not cards:
        cards = soup.select(".game-cell")
    if not cards:
        cards = soup.select(".game_grid_widget .game_cell")
    return cards


def next_page_url(soup: BeautifulSoup, current_url: str, page_number: int) -> str | None:
    """Prefer the site's Next page link; use ?page=N only as a fallback."""
    for link in soup.select("a.next_page, a[rel='next']"):
        href = link.get("href")
        if href:
            return urljoin(current_url, href)
    # The listing uses a page query parameter. Stop if no cards are returned.
    from urllib.parse import parse_qs, urlunparse
    parts = urlparse(current_url)
    query = parse_qs(parts.query)
    query["page"] = [str(page_number + 1)]
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def scrape_top_sellers() -> list[dict]:
    """Collect up to 500 distinct games, preserving the site's current rank order."""
    global ROBOTS_LINES
    # Fetch robots.txt once and cache the rules for URL checks in get_page().
    robots_response = session.get(ROBOTS_URL, timeout=20)
    global request_count, last_request_at
    request_count += 1
    last_request_at = time.monotonic()
    robots_response.raise_for_status()
    ROBOTS_LINES = robots_response.text.splitlines()
    robots = RobotFileParser()
    robots.parse(ROBOTS_LINES)
    if not robots.can_fetch(USER_AGENT, BASE_URL):
        raise RuntimeError("robots.txt disallows the listing page; scraper stopped.")
    logging.info("robots.txt allows the top-sellers listing URL.")

    rows = []
    seen_urls = set()
    url = BASE_URL
    page_number = 1
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    while url and len(rows) < TARGET_COUNT:
        logging.info("Fetching listing page %s: %s", page_number, url)
        soup = get_page(url)
        cards = find_cards(soup)
        if not cards:
            logging.warning("No game cards found on page %s; stopping. HTML may have changed.", page_number)
            break

        for card in cards:
            # Avoid duplicates if a page repeats a game or pagination redirects.
            title_link = card.select_one("a.title") or card.select_one(".game_title a")
            href = urljoin(url, title_link.get("href", "")) if title_link else None
            if href and href in seen_urls:
                continue
            if href:
                seen_urls.add(href)
            row = parse_game_card(card, len(rows) + 1, url, scraped_at)
            if row["title"]:
                rows.append(row)
            if len(rows) >= TARGET_COUNT:
                break

        logging.info("Collected %s/%s games after page %s.", len(rows), TARGET_COUNT, page_number)
        if len(rows) >= TARGET_COUNT:
            break
        url = next_page_url(soup, url, page_number)
        page_number += 1

    if len(rows) < TARGET_COUNT:
        logging.warning("Only %s records collected; check layout, pagination, and site availability.", len(rows))
    return rows


def save_raw_files(rows: list[dict], run_time: datetime) -> tuple[Path, Path]:
    """Save an unchanged CSV and JSON snapshot for evidence of this daily run."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = run_time.strftime("%Y-%m-%d")
    csv_path = RAW_DIR / f"itchio_top_sellers_{stamp}.csv"
    json_path = RAW_DIR / f"itchio_top_sellers_{stamp}.json"
    # UTF-8-SIG makes CSV open cleanly in common spreadsheet applications.
    fields = list(rows[0].keys()) if rows else ["rank", "title", "developer", "price", "genre", "platforms", "game_url", "listing_page", "scraped_at"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    logging.info("Saved raw evidence: %s and %s", csv_path, json_path)
    return csv_path, json_path


def clean_price(price: str | None) -> float | None:
    """Extract a numeric amount when a displayed price contains one; otherwise None."""
    if not price or price.lower().startswith("free") or "no price" in price.lower():
        return 0.0 if price and price.lower().startswith("free") else None
    # This stores a numeric amount where possible; original displayed price remains in raw CSV/JSON.
    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", price.replace(",", ""))
    return float(match.group(0)) if match else None


def save_cleaned_and_database(rows: list[dict]) -> None:
    """Create a cleaned CSV and normalized SQLite tables for repeatable analysis."""
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_rows = []
    for row in rows:
        cleaned = dict(row)
        cleaned["price_value"] = clean_price(row.get("price"))
        # Standardize blank values as None rather than the strings 'None' or 'nan'.
        for field in ("title", "developer", "genre", "platforms", "game_url"):
            if not cleaned.get(field):
                cleaned[field] = None
        cleaned_rows.append(cleaned)

    # Save a separate cleaned file; never overwrite the raw evidence files.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    clean_path = CLEAN_DIR / f"itchio_top_sellers_cleaned_{stamp}.csv"
    if cleaned_rows:
        with clean_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(cleaned_rows[0].keys()))
            writer.writeheader()
            writer.writerows(cleaned_rows)

    # products holds stable identity; observations holds rank/price as seen each day.
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS products (
            game_url TEXT PRIMARY KEY, title TEXT, developer TEXT, genre TEXT, platforms TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_url TEXT NOT NULL, rank INTEGER, price_text TEXT, price_value REAL,
            listing_page TEXT, scraped_at TEXT,
            FOREIGN KEY(game_url) REFERENCES products(game_url)
        )""")
        for row in cleaned_rows:
            game_url = row.get("game_url") or f"unknown-rank-{row['rank']}"
            connection.execute(
                "INSERT INTO products(game_url,title,developer,genre,platforms) VALUES(?,?,?,?,?) "
                "ON CONFLICT(game_url) DO UPDATE SET title=excluded.title, developer=excluded.developer, "
                "genre=excluded.genre, platforms=excluded.platforms",
                (game_url, row.get("title"), row.get("developer"), row.get("genre"), row.get("platforms")),
            )
            connection.execute(
                "INSERT INTO observations(game_url,rank,price_text,price_value,listing_page,scraped_at) VALUES(?,?,?,?,?,?)",
                (game_url, row.get("rank"), row.get("price"), row.get("price_value"), row.get("listing_page"), row.get("scraped_at")),
            )
    logging.info("Saved cleaned CSV: %s", clean_path)
    logging.info("Updated SQLite database: %s", DB_PATH)


def main() -> None:
    """Run one daily collection, save raw evidence, clean data, and update SQLite."""
    run_time = datetime.now(timezone.utc)
    rows = scrape_top_sellers()
    if not rows:
        raise RuntimeError("No data collected. Check logs and do not submit an empty run as success.")
    save_raw_files(rows, run_time)
    save_cleaned_and_database(rows)
    logging.info("Finished: %s records collected; %s HTTP requests used.", len(rows), request_count)


# Cached robots rules used by get_page(); populated before the first listing request.
ROBOTS_LINES: list[str] = []

if __name__ == "__main__":
    main()

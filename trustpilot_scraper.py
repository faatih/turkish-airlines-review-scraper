import requests
from bs4 import BeautifulSoup
import json
import csv
from openpyxl import Workbook
import time
import logging
import argparse
from datetime import datetime
import html
import random

# --- Constants ---
TRUSTPILOT_BASE_URL = "https://www.trustpilot.com/review/www.turkishairlines.com"
DEFAULT_CSV_FILENAME = "turkish_airlines_trustpilot_reviews.csv"
DEFAULT_EXCEL_FILENAME = "turkish_airlines_trustpilot_reviews.xlsx"
DEFAULT_MAX_PAGES = 0 # 0 means scrape all available pages

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- User Agent ---
# Use a common user agent to mimic a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
}

# --- Parse Function ---
def parse_trustpilot_review_data(review_json):
    """Helper function to parse a single review JSON object from Trustpilot __NEXT_DATA__."""
    review_data = {}

    # Extract data using .get() to avoid KeyErrors if fields are missing
    review_data['id'] = review_json.get('id') # Unique review ID from Trustpilot
    consumer = review_json.get('consumer', {})
    review_data['author'] = consumer.get('displayName')
    review_data['consumer_id'] = consumer.get('id') # Can be useful
    review_data['consumer_reviews_count'] = consumer.get('numberOfReviews')
    review_data['consumer_country'] = consumer.get('countryCode')

    dates = review_json.get('dates', {})
    published_date_str = dates.get('publishedDate')
    experienced_date_str = dates.get('experiencedDate')

    # Parse dates (Trustpilot uses ISO 8601 format with timezone)
    try:
        # Remove the 'Z' and parse
        dt_obj = datetime.fromisoformat(published_date_str.replace('Z', '+00:00'))
        review_data['date_published'] = dt_obj.strftime('%Y-%m-%d %H:%M:%S') # Store in a standard format
    except (ValueError, TypeError):
        logging.warning(f"Could not parse published date: {published_date_str}. Storing raw.")
        review_data['date_published'] = published_date_str

    try:
        dt_obj = datetime.fromisoformat(experienced_date_str.replace('Z', '+00:00'))
        review_data['date_experience'] = dt_obj.strftime('%Y-%m-%d') # Store date part only
    except (ValueError, TypeError):
        logging.warning(f"Could not parse experience date: {experienced_date_str}. Storing raw.")
        review_data['date_experience'] = experienced_date_str


    review_data['rating'] = review_json.get('rating')
    review_data['title'] = review_json.get('title')

    raw_body = review_json.get('text', '')
    # Trustpilot text often contains <br>, replace with newline and decode entities
    soup = BeautifulSoup(raw_body.replace('<br />', '\n').replace('<br>', '\n'), 'html.parser')
    review_data['body'] = html.unescape(soup.get_text(separator='\n').strip())

    review_data['language'] = review_json.get('language')
    review_data['likes'] = review_json.get('likes', 0)

    # Check verification status if needed (might require deeper inspection of 'labels')
    verification_info = review_json.get('labels', {}).get('verification', {})
    review_data['is_verified'] = verification_info.get('isVerified', False)
    review_data['verification_source'] = verification_info.get('reviewSourceName', 'Unknown')


    return review_data


# --- Requests-based Extraction Function ---
def extract_trustpilot_reviews(base_url, max_pages):
    """
    Extracts Turkish Airlines reviews from Trustpilot using requests and BeautifulSoup.

    Args:
        base_url (str): The base URL of the Trustpilot review page.
        max_pages (int): Maximum number of pages to scrape (0 for all).

    Returns:
        list: A list of review dictionaries (or an empty list on failure).
    """
    all_reviews_data = []
    processed_review_ids = set()
    current_page = 1
    total_pages = 1 # Start assuming one page

    while True:
        page_url = f"{base_url}?page={current_page}"
        logging.info(f"Requesting page: {page_url}")

        try:
            response = requests.get(page_url, headers=HEADERS, timeout=20) # Added timeout
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch {page_url}: {e}")
            break # Stop if a page fails to load

        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')

            if not script_tag:
                logging.warning(f"Could not find __NEXT_DATA__ script tag on page {current_page}. Stopping.")
                break

            page_data = json.loads(script_tag.string)
            reviews_on_page = page_data.get('props', {}).get('pageProps', {}).get('reviews', [])

            # Get total pages on the first iteration
            if current_page == 1:
                try:
                    total_pages = page_data['props']['pageProps']['filters']['pagination']['totalPages']
                    logging.info(f"Found {total_pages} total pages.")
                    if max_pages > 0:
                         total_pages = min(total_pages, max_pages) # Respect max_pages limit
                         logging.info(f"Will scrape up to {total_pages} pages based on limit.")
                except (KeyError, TypeError):
                     logging.warning("Could not determine total pages from page data. Scraping page by page until no new reviews are found or max_pages is hit.")
                     # If totalPages isn't found, rely on max_pages or finding no reviews
                     if max_pages == 0: max_pages = 1000 # Set a high arbitrary limit if not found and no user limit

            if not reviews_on_page:
                logging.info(f"No reviews found on page {current_page}. Assuming end of reviews.")
                break

            new_reviews_found_on_page = 0
            for review_json in reviews_on_page:
                review_data = parse_trustpilot_review_data(review_json)
                if review_data and review_data['id'] not in processed_review_ids:
                    all_reviews_data.append(review_data)
                    processed_review_ids.add(review_data['id'])
                    new_reviews_found_on_page += 1

            logging.info(f"Extracted {new_reviews_found_on_page} new reviews from page {current_page}. Total unique reviews: {len(all_reviews_data)}")

            # Stop if we've reached the determined total pages or max_pages limit
            if current_page >= total_pages:
                 logging.info(f"Reached target page count ({total_pages}). Stopping.")
                 break

            current_page += 1
            # Add a polite random delay between requests
            time.sleep(random.uniform(1.0, 2.5))

        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON data from __NEXT_DATA__ on page {current_page}.")
            break # Stop if JSON is invalid
        except Exception as e:
            logging.error(f"An unexpected error occurred processing page {current_page}: {e}", exc_info=True)
            break # Stop on unexpected errors

    # Remove temporary ID before returning
    for review in all_reviews_data:
        review.pop('id', None) # Remove the Trustpilot internal ID if desired
        review.pop('consumer_id', None) # Remove consumer ID if desired

    return all_reviews_data

# --- CSV and Excel writing functions (remain the same, ensure robustness) ---
def write_reviews_to_csv(reviews, filename):
    if not reviews:
        logging.warning("No reviews provided to write_reviews_to_csv.")
        return
    fieldnames = set()
    for review in reviews:
        fieldnames.update(review.keys())
    fieldnames = sorted(list(fieldnames))

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(reviews)
        logging.info(f"Successfully wrote {len(reviews)} reviews to {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV file '{filename}': {e}", exc_info=True)

def write_reviews_to_excel(reviews, filename):
    if not reviews:
        logging.warning("No reviews provided to write_reviews_to_excel.")
        return
    fieldnames = set()
    for review in reviews:
        fieldnames.update(review.keys())
    fieldnames = sorted(list(fieldnames))

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Reviews"
        ws.append(fieldnames)

        for review in reviews:
            row = [review.get(field, "") for field in fieldnames]
            ws.append(row)

        wb.save(filename)
        logging.info(f"Successfully wrote {len(reviews)} reviews to {filename}")
    except Exception as e:
       logging.error(f"Error writing to Excel file '{filename}': {e}", exc_info=True)


# --- Main Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Turkish Airlines reviews from Trustpilot.")
    parser.add_argument("-u", "--url", default=TRUSTPILOT_BASE_URL, help="Base URL of the Trustpilot review page.")
    parser.add_argument("-p", "--pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum number of pages to scrape (0 for all).")
    parser.add_argument("-c", "--csv", default=DEFAULT_CSV_FILENAME, help="Output CSV filename.")
    parser.add_argument("-x", "--excel", default=DEFAULT_EXCEL_FILENAME, help="Output Excel filename.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging level.")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("DEBUG logging enabled.")

    logging.info("Starting Trustpilot review scraping process...")
    extracted_reviews = extract_trustpilot_reviews(args.url, args.pages)

    if extracted_reviews:
        logging.info(f"Total unique reviews extracted: {len(extracted_reviews)}")
        write_reviews_to_csv(extracted_reviews, args.csv)
        write_reviews_to_excel(extracted_reviews, args.excel)
    else:
        logging.warning("No reviews were extracted or an error occurred.")

    logging.info("Scraping process finished.")
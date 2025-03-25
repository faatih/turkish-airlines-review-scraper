import requests
from bs4 import BeautifulSoup
import json
import csv
from openpyxl import Workbook # Make sure openpyxl is installed: pip install openpyxl
import time
import logging
import argparse
from datetime import datetime
import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException, StaleElementReferenceException
import random # For randomized delays

# --- Constants ---
BASE_URL = "https://www.trustindex.io/reviews/turkish-airline.com"
DEFAULT_MAX_LOOPS = 10
DEFAULT_CSV_FILENAME = "turkish_airlines_reviews.csv"
DEFAULT_EXCEL_FILENAME = "turkish_airlines_reviews.xlsx"
MORE_BUTTON_SELECTOR = '#next-button > a.page-link'
REVIEW_DIV_SELECTOR = 'div.review'
# Increase wait times slightly
WAIT_TIMEOUT_GENERAL = 25
WAIT_TIMEOUT_STABILIZE = 15

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Parse Function ---
def parse_review_div(review_div):
    """Helper function to parse a single review div element."""
    review_data = {}
    # Use .get() with a default to avoid KeyError if 'data-id' is missing
    review_id = review_div.get('data-id')
    if not review_id:
        logging.warning("Found review div without data-id, skipping.")
        return None

    review_data['review_id'] = review_id

    try:
        review_data['author'] = review_div.find('div', class_='ti-name').text.strip()
    except AttributeError:
        review_data['author'] = None
        logging.debug(f"Could not find author for review {review_id}")

    try:
        date_str = review_div.find('div', class_='ti-date').text.strip()
        try:
            dt_obj = datetime.strptime(date_str, '%Y.%m.%d')
            review_data['date'] = dt_obj.strftime('%Y-%m-%d') # Store in ISO format
        except ValueError:
            logging.warning(f"Could not parse date string: {date_str} for review {review_id}. Storing raw.")
            review_data['date'] = date_str
    except AttributeError:
        review_data['date'] = None
        logging.debug(f"Could not find date for review {review_id}")

    try:
        # More robust rating extraction: handle cases with 0 stars
        star_container = review_div.find('div', class_='ti-stars')
        if star_container:
             review_data['rating'] = len(star_container.find_all('span', class_='ti-star f'))
        else:
             review_data['rating'] = None # Or 0 if appropriate
             logging.debug(f"Could not find star container for review {review_id}")
    except Exception as e: # Catch broader exceptions during parsing
        review_data['rating'] = None
        logging.warning(f"Error parsing rating for review {review_id}: {e}")

    try:
        content_div = review_div.find('div', class_='ti-review-content')
        if content_div:
            for br in content_div.find_all('br'):
                br.replace_with('\n')
            raw_body = content_div.text.strip()
            review_data['body'] = html.unescape(raw_body)
        else:
            review_data['body'] = None
            logging.debug(f"Could not find body div for review {review_id}")
    except AttributeError:
        review_data['body'] = None
        logging.debug(f"Could not find/parse body for review {review_id}")

    try:
        source_class = review_div.get('class', []) # Use .get with default empty list
        review_data['source_platform'] = next((s.replace('source-', '') for s in source_class if s.startswith('source-')), 'Unknown')
    except StopIteration:
         review_data['source_platform'] = 'Unknown'
         logging.debug(f"Could not determine source platform class for review {review_id}")
    except Exception as e:
         review_data['source_platform'] = 'Unknown'
         logging.warning(f"Error getting source platform for review {review_id}: {e}")


    return review_data

# --- Selenium Extraction Function ---
def extract_reviews_selenium(url, max_loops):
    extracted_review_ids = set()
    all_reviews_data = []
    driver = None

    try:
        # --- Chrome Options ---
        chrome_options = Options()
        # chrome_options.add_argument("--headless=new") # Try the newer headless mode syntax
        chrome_options.add_argument("--headless") # Fallback if new syntax fails
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1200") # Slightly larger height
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled") # Try to hide automation
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation","enable-logging"]) # Further hide automation
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36") # Use a common, recent user agent

        logging.info(f"Initializing Selenium WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
        # Set longer implicit wait? Sometimes helpful, sometimes hides issues. Let's stick to explicit for now.
        # driver.implicitly_wait(5)
        wait = WebDriverWait(driver, WAIT_TIMEOUT_GENERAL)
        stabilize_wait = WebDriverWait(driver, WAIT_TIMEOUT_STABILIZE)

        logging.info(f"Loading page: {url}")
        driver.get(url)
        # Add a small wait after initial load for elements to potentially settle
        time.sleep(2)
        logging.info("Page loaded.")

        # --- Helper to get review divs from current page source ---
        def get_review_divs_from_source(page_source):
            try:
                soup = BeautifulSoup(page_source, 'html.parser')
                return soup.select(REVIEW_DIV_SELECTOR)
            except Exception as e:
                logging.error(f"Error parsing page source with BeautifulSoup: {e}")
                return []

        # --- Initial extraction ---
        logging.info("Extracting initial reviews...")
        initial_divs = get_review_divs_from_source(driver.page_source)
        initial_count = 0
        for div in initial_divs:
            review_data = parse_review_div(div)
            if review_data and review_data['review_id'] and review_data['review_id'] not in extracted_review_ids:
                all_reviews_data.append(review_data)
                extracted_review_ids.add(review_data['review_id'])
                initial_count += 1
        logging.info(f"Extracted {initial_count} initial reviews.")
        last_known_review_id_count = len(extracted_review_ids)

        loop_count = 0
        while loop_count < max_loops:
            num_reviews_before_click = len(driver.find_elements(By.CSS_SELECTOR, REVIEW_DIV_SELECTOR))
            logging.debug(f"Review divs found before click {loop_count+1}: {num_reviews_before_click}")

            try:
                logging.info(f"Attempting click loop {loop_count + 1}/{max_loops}")
                more_button_locator = (By.CSS_SELECTOR, MORE_BUTTON_SELECTOR)

                # 1. Wait for button visibility/presence
                try:
                    more_button = wait.until(EC.presence_of_element_located(more_button_locator))
                    logging.debug("More button present.")
                except TimeoutException:
                    logging.info("Timeout waiting for 'More' button presence. Assuming end of reviews.")
                    break

                # 2. Scroll into view
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", more_button)
                    time.sleep(random.uniform(0.5, 1.0)) # Random small delay after scroll
                    logging.debug("Scrolled button into view.")
                except Exception as scroll_e:
                    logging.warning(f"Could not scroll button into view: {scroll_e}. Proceeding anyway.")

                # 3. Wait for clickability
                try:
                     more_button = wait.until(EC.element_to_be_clickable(more_button_locator))
                     logging.debug("More button is clickable.")
                except TimeoutException:
                     logging.warning("Timeout waiting for 'More' button to be clickable after scroll. Attempting click anyway.")
                     # Re-find element in case it became stale after scroll
                     more_button = driver.find_element(*more_button_locator)


                # 4. Click attempt
                try:
                    logging.debug("Attempting direct click...")
                    more_button.click()
                except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                    logging.warning(f"Direct click failed ({type(e).__name__}), trying JavaScript click...")
                    time.sleep(random.uniform(1.0, 2.0))
                    try:
                        # It's crucial to re-find the element before JS click if direct click failed
                        more_button = wait.until(EC.presence_of_element_located(more_button_locator))
                        driver.execute_script("arguments[0].click();", more_button)
                    except Exception as js_e:
                        logging.error(f"JavaScript click also failed: {js_e}")
                        break

                logging.info("Clicked 'More' button. Waiting for new reviews to load...")

                # 5. --- Wait for content to actually load ---
                try:
                    # Primary strategy: Wait for the count to increase
                    wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, REVIEW_DIV_SELECTOR)) > num_reviews_before_click)
                    new_review_dom_count = len(driver.find_elements(By.CSS_SELECTOR, REVIEW_DIV_SELECTOR))
                    logging.info(f"Detected an increase in review count to {new_review_dom_count}.")

                    # Secondary stabilization: Wait for the *last* new element to be present
                    last_element_xpath = f"({REVIEW_DIV_SELECTOR})[{new_review_dom_count}]"
                    try:
                         stabilize_wait.until(EC.presence_of_element_located((By.XPATH, last_element_xpath)))
                         logging.debug(f"Last expected review element ({new_review_dom_count}) is present.")
                         time.sleep(random.uniform(0.5, 1.0)) # Short randomized delay after stabilization
                    except TimeoutException:
                         logging.warning(f"Timed out waiting for the last element ({new_review_dom_count}) to stabilize. Parsing might be incomplete.")
                         # Continue but be aware

                except TimeoutException:
                    # Count didn't increase. Check if button is gone.
                    logging.debug("Timeout waiting for review count to increase.")
                    try:
                        # Check if button still exists *and* is visible
                        if driver.find_element(*more_button_locator).is_displayed():
                             logging.info("Review count did not increase after click, button still visible. Assuming end of reviews or load error.")
                        else:
                             logging.info("Review count did not increase, button is no longer visible. Assuming end of reviews.")
                    except NoSuchElementException:
                        logging.info("Review count did not increase and 'More' button disappeared. Assuming end of reviews.")
                    break # Exit outer loop


                # 6. --- Extract ONLY newly loaded reviews ---
                current_divs = get_review_divs_from_source(driver.page_source)
                newly_loaded_reviews_in_loop = 0
                for div in current_divs:
                    review_data = parse_review_div(div)
                    if review_data and review_data['review_id'] and review_data['review_id'] not in extracted_review_ids:
                        all_reviews_data.append(review_data)
                        extracted_review_ids.add(review_data['review_id'])
                        newly_loaded_reviews_in_loop += 1

                logging.info(f"Extracted {newly_loaded_reviews_in_loop} new reviews in this loop. Total unique reviews: {len(extracted_review_ids)}")
                current_unique_count = len(extracted_review_ids)

                # Check if no *new unique* reviews were added
                if current_unique_count == last_known_review_id_count:
                     # This condition might be hit if the stabilization wait wasn't enough,
                     # or if the page loaded duplicates briefly that were filtered out.
                     logging.warning("DOM count may have increased, but no new *unique* reviews were parsed. Stopping to prevent infinite loop.")
                     break

                last_known_review_id_count = current_unique_count # Update the count

                loop_count += 1
                # Random delay before next loop
                time.sleep(random.uniform(1.5, 3.0))

            # Outer loop exceptions
            except TimeoutException as e_outer:
                logging.info(f"TimeoutException during button interaction (Outer try): {e_outer}. Assuming end of reviews.")
                break
            except NoSuchElementException as e_outer:
                logging.info(f"NoSuchElementException during button interaction (Outer try): {e_outer}. Assuming end of reviews.")
                break
            except Exception as e_outer:
                logging.error(f"An unexpected error occurred during the loop: {e_outer}", exc_info=True)
                break

    except Exception as e_setup:
        logging.error(f"An error occurred during Selenium setup or initial load: {e_setup}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logging.info("Browser closed.")

    # Remove temporary ID before returning
    for review in all_reviews_data:
        review.pop('review_id', None)

    return all_reviews_data


# --- CSV/Excel Writing Functions ---
# (Keep the robust versions from the previous answer that handle missing keys)
def write_reviews_to_csv(reviews, filename):
    """Writes extracted reviews to CSV."""
    if not reviews:
        logging.warning("No reviews provided to write_reviews_to_csv.")
        return
    fieldnames = set()
    for review in reviews:
        fieldnames.update(review.keys())
    fieldnames = sorted(list(fieldnames)) # Ensure consistent order

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Use ignore for extrasaction if some dicts might miss keys compared to others
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(reviews)
        logging.info(f"Successfully wrote {len(reviews)} reviews to {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV file '{filename}': {e}", exc_info=True)

def write_reviews_to_excel(reviews, filename):
    """Writes extracted reviews to Excel."""
    if not reviews:
        logging.warning("No reviews provided to write_reviews_to_excel.")
        return
    fieldnames = set()
    for review in reviews:
        fieldnames.update(review.keys())
    fieldnames = sorted(list(fieldnames)) # Ensure consistent order

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Reviews"
        ws.append(fieldnames) # Write header

        for review in reviews:
            # Build row ensuring value exists for each fieldname, default to empty string
            row = [review.get(field, "") for field in fieldnames]
            ws.append(row)

        wb.save(filename)
        logging.info(f"Successfully wrote {len(reviews)} reviews to {filename}")
    except Exception as e:
       logging.error(f"Error writing to Excel file '{filename}': {e}", exc_info=True)


# --- Main Execution Block with Argparse ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Turkish Airlines reviews from Trustindex.")
    parser.add_argument("-u", "--url", default=BASE_URL, help="URL of the Trustindex review page.")
    parser.add_argument("-l", "--loops", type=int, default=DEFAULT_MAX_LOOPS, help="Maximum number of 'More' clicks.")
    parser.add_argument("-c", "--csv", default=DEFAULT_CSV_FILENAME, help="Output CSV filename.")
    parser.add_argument("-x", "--excel", default=DEFAULT_EXCEL_FILENAME, help="Output Excel filename.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging level.")
    # Add option to run non-headless for debugging
    parser.add_argument("--show-browser", action="store_true", help="Run with a visible browser window instead of headless.")


    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("DEBUG logging enabled.")

    # --- Modify Options based on args ---
    chrome_options = Options()
    if not args.show_browser: # Only add headless if --show-browser is NOT used
        # chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation","enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36") # Use a common, recent user agent

    # --- Call extraction function (pass modified options if needed, though it's self-contained now) ---
    logging.info("Starting review scraping process...")
    # The extract_reviews_selenium function now configures its own options
    extracted_reviews = extract_reviews_selenium(args.url, args.loops) # We now pass the configured options

    if extracted_reviews:
        logging.info(f"Total unique reviews extracted: {len(extracted_reviews)}")
        write_reviews_to_csv(extracted_reviews, args.csv)
        write_reviews_to_excel(extracted_reviews, args.excel)
    else:
        logging.warning("No reviews were extracted.")

    logging.info("Scraping process finished.")
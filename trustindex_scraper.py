from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
import json
import csv
from openpyxl import Workbook # Make sure openpyxl is installed: pip install openpyxl
import time

def parse_review_div(review_div):
    """Helper function to parse a single review div element."""
    try:
        author = review_div.find('div', class_='ti-name').text.strip()
    except AttributeError:
        author = None
    try:
        date = review_div.find('div', class_='ti-date').text.strip()
    except AttributeError:
        date = None
    try:
        # Count the number of 'ti-star f' (filled) stars
        rating = len(review_div.find('div', class_='ti-stars').find_all('span', class_='ti-star f'))
    except AttributeError:
        rating = None
    try:
        # Extract text, handling potential <br> tags for line breaks
        content_div = review_div.find('div', class_='ti-review-content')
        # Replace <br> with newline, then get text and strip whitespace
        for br in content_div.find_all('br'):
            br.replace_with('\n')
        body = content_div.text.strip()
    except AttributeError:
        body = None
    try:
        # Attempt to get source from the platform icon class if available, fallback needed
        source_class = review_div['class'] # Get all classes of the review div
        source = next((s.replace('source-', '') for s in source_class if s.startswith('source-')), 'Unknown')
    except (AttributeError, KeyError):
         source = 'Unknown' # Fallback if no source class found

    # Get the unique review ID for deduplication
    review_id = review_div.get('data-id')

    return {
        'review_id': review_id, # Add review_id for deduplication
        'author': author,
        'date': date,
        'rating': rating,
        'body': body,
        'source_platform': source
    }


def extract_reviews_selenium(url, max_loops=10):
    """
    Extracts Turkish Airlines reviews using Selenium, targeting HTML elements directly
    after clicking the 'More' button.

    Args:
        url (str): The URL of the Trustindex.io page.
        max_loops (int): The maximum number of "More" button clicks.

    Returns:
        list: A list of review dictionaries (or an empty list on failure).
    """
    extracted_review_ids = set() # Keep track of extracted review IDs to avoid duplicates
    all_reviews_data = []

    try:
        # Configure Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080") # Set a reasonable window size
        chrome_options.add_argument("--no-sandbox") # Often needed in containerized/Linux environments
        chrome_options.add_argument("--disable-dev-shm-usage") # Overcomes limited resource problems
        chrome_options.add_argument("--log-level=3") # Suppress unnecessary console logs from Chrome/Driver
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        print("Page loaded.")

        # Initial extraction from the first page load
        print("Extracting initial reviews...")
        initial_soup = BeautifulSoup(driver.page_source, 'html.parser')
        review_divs = initial_soup.find_all('div', class_='review') # Find review containers
        for div in review_divs:
            review_data = parse_review_div(div)
            if review_data and review_data['review_id'] and review_data['review_id'] not in extracted_review_ids:
                all_reviews_data.append(review_data)
                extracted_review_ids.add(review_data['review_id'])
        print(f"Extracted {len(all_reviews_data)} initial reviews.")


        loop_count = 0
        while loop_count < max_loops:
            try:
                print(f"\nAttempting loop {loop_count + 1}/{max_loops}")
                # Use a more specific CSS selector and wait for clickability
                more_button_locator = (By.CSS_SELECTOR, '#next-button > a.page-link')
                more_button = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable(more_button_locator)
                )

                # Scroll the button into view
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", more_button)
                time.sleep(0.5) # Short pause after scroll

                # Try direct click first, fallback to JavaScript click
                try:
                    print("Attempting direct click...")
                    more_button.click()
                except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                    print(f"Direct click failed ({type(e).__name__}), trying JavaScript click...")
                    time.sleep(1) # Wait a moment before JS click
                    # Re-find the element in case it went stale
                    more_button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(more_button_locator) # Wait for presence this time
                    )
                    driver.execute_script("arguments[0].click();", more_button)

                print("Clicked 'More' button.")
                time.sleep(3) # Increase wait time after click for content to load

                # --- Extract ONLY newly loaded reviews ---
                current_soup = BeautifulSoup(driver.page_source, 'html.parser')
                newly_loaded_reviews = 0
                review_divs = current_soup.find_all('div', class_='review')
                for div in review_divs:
                    review_data = parse_review_div(div)
                    # Add only if we have an ID and haven't seen it before
                    if review_data and review_data['review_id'] and review_data['review_id'] not in extracted_review_ids:
                        all_reviews_data.append(review_data)
                        extracted_review_ids.add(review_data['review_id'])
                        newly_loaded_reviews += 1

                print(f"Extracted {newly_loaded_reviews} new reviews in this loop. Total unique reviews: {len(all_reviews_data)}")

                if newly_loaded_reviews == 0:
                     print("No new reviews loaded in this loop, likely reached the end.")
                     break # Exit if no new reviews were found after clicking

                loop_count += 1

            except TimeoutException:
                print("TimeoutException: 'More' button not found or not clickable after waiting. Assuming end of reviews.")
                break
            except NoSuchElementException:
                print("NoSuchElementException: 'More' button not found. Assuming end of reviews.")
                break
            except Exception as e:
                print(f"An unexpected error occurred during the loop: {e}")
                break

    except Exception as e:
        print(f"An error occurred during Selenium setup or initial load: {e}")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()
            print("Browser closed.")

    # Remove the temporary review_id before returning/saving
    for review in all_reviews_data:
        review.pop('review_id', None)

    return all_reviews_data

# --- CSV and Excel writing functions remain the same ---
def write_reviews_to_csv(reviews, filename="turkish_airlines_reviews.csv"):
    """Writes extracted reviews to CSV."""
    if not reviews:
        print("No reviews to write.")
        return
    # Ensure all dicts have the same keys for DictWriter, handle potential missing keys
    fieldnames = set()
    for review in reviews:
        fieldnames.update(review.keys())
    fieldnames = sorted(list(fieldnames)) # Ensure consistent order

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') # Ignore extra fields if any dict has fewer keys
            writer.writeheader()
            writer.writerows(reviews)
        print(f"Successfully wrote reviews to {filename}")
    except Exception as e:
        print(f"Error writing to CSV file: {e}")

def write_reviews_to_excel(reviews, filename="turkish_airlines_reviews2.xlsx"):
    """Writes extracted reviews to Excel."""
    if not reviews:
        print("No reviews to write.")
        return

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Reviews"

        # Ensure all dicts have the same keys for header, handle potential missing keys
        fieldnames = set()
        for review in reviews:
            fieldnames.update(review.keys())
        fieldnames = sorted(list(fieldnames)) # Ensure consistent order

        ws.append(fieldnames) # Write header

        for review in reviews:
            # Build row ensuring value exists for each fieldname, default to empty string if missing
            row = [review.get(field, "") for field in fieldnames]
            ws.append(row)

        wb.save(filename)
        print(f"Successfully wrote reviews to {filename}")
    except Exception as e:
        print(f"Error writing to Excel file: {e}")


# Example Usage:
trustindex_url = "https://www.trustindex.io/reviews/turkish-airline.com"
# Start with a smaller max_loops for testing, e.g., 3, then increase
reviews = extract_reviews_selenium(trustindex_url, max_loops=10)

if reviews:
    print(f"\nTotal unique reviews extracted: {len(reviews)}")
    # write_reviews_to_csv(reviews)
    write_reviews_to_excel(reviews)
else:
    print("\nNo reviews extracted or an error occurred.")
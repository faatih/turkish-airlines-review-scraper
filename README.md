
# Turkish Airlines Review Scraper (Trustindex.io)

This Python script scrapes customer reviews for Turkish Airlines from their profile page on Trustindex.io (`https://www.trustindex.io/reviews/turkish-airline.com`). It uses Selenium to automate a web browser, handling the dynamic loading ("More" button clicks) required to fetch all available reviews up to a specified limit. The scraped data includes the reviewer's name, review date, rating, review body, and the source platform indicated on Trustindex. The extracted reviews are saved into both CSV and Excel (.xlsx) formats.

## Features

*   Scrapes reviews from the specified Trustindex.io URL.
*   Uses Selenium to automate browser interaction and handle AJAX-based pagination ("More" button clicks).
*   Extracts the following fields for each review:
    *   Author Name
    *   Review Date (parsed into YYYY-MM-DD format where possible)
    *   Rating (1-5 stars)
    *   Review Body (with basic HTML entity decoding)
    *   Source Platform (e.g., Tripadvisor, Yelp, as listed on Trustindex)
*   Implements deduplication based on unique review IDs found on the page.
*   Saves the scraped data into both `.csv` and `.xlsx` files.
*   Allows configuration of the target URL, maximum "More" clicks, and output filenames via command-line arguments.
*   Includes options for verbose logging and running the browser visibly (non-headless) for debugging.

## Technology Stack

*   **Python 3.x**
*   **Selenium:** For browser automation and handling dynamic content.
*   **BeautifulSoup4:** For parsing HTML content retrieved by Selenium.
*   **openpyxl:** For writing data to Excel (.xlsx) files.
*   **ChromeDriver:** Required by Selenium to control the Chrome browser.

## Setup and Installation

1.  **Prerequisites:**
    *   **Git:** Ensure Git is installed ([https://git-scm.com/](https://git-scm.com/)).
    *   **Python 3:** Ensure Python 3.x is installed ([https://www.python.org/](https://www.python.org/)).
    *   **Google Chrome:** Ensure you have Google Chrome browser installed.

2.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url> # Replace with your actual GitHub repo URL
    cd <repository-name>            # Navigate into the cloned project directory
    ```

3.  **Create and Activate Virtual Environment:** (Recommended)
    ```bash
    # Create the virtual environment (use python3 if needed)
    python -m venv .venv

    # Activate it:
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

4.  **Install Dependencies:**
    *   Create a `requirements.txt` file with the following content:
        ```txt
        selenium
        beautifulsoup4
        openpyxl
        requests 
        ```
    *   Install the required packages:
        ```bash
        pip install -r requirements.txt
        ```

5.  **Download ChromeDriver:**
    *   Check your installed Google Chrome version (Help -> About Google Chrome).
    *   Download the matching version of ChromeDriver from: [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads)
    *   Place the `chromedriver.exe` (Windows) or `chromedriver` (macOS/Linux) executable either:
        *   In the same directory as your Python script (`trustindex_scraper2.py`).
        *   OR in a directory that is listed in your system's `PATH` environment variable.

## Usage

Run the script from your terminal within the activated virtual environment.

**Basic Usage (Defaults):**

```bash
python trustindex_scraper2.py
```

This will:
*   Scrape reviews from the default Trustindex URL.
*   Click the "More" button up to 10 times (default `max_loops`).
*   Save results to `turkish_airlines_reviews.csv` and `turkish_airlines_reviews.xlsx`.

**Command-Line Arguments:**

*   `-u URL, --url URL`: Specify the Trustindex review page URL.
    *   Example: `python trustindex_scraper2.py --url "https://another-trustindex-url.com"`
*   `-l LOOPS, --loops LOOPS`: Set the maximum number of times to click the "More" button.
    *   Example: `python trustindex_scraper2.py --loops 25`
*   `-c CSV, --csv CSV`: Specify the output CSV filename.
    *   Example: `python trustindex_scraper2.py --csv output_reviews.csv`
*   `-x EXCEL, --excel EXCEL`: Specify the output Excel filename.
    *   Example: `python trustindex_scraper2.py --excel output_reviews.xlsx`
*   `-v, --verbose`: Enable detailed DEBUG logging output to the console.
    *   Example: `python trustindex_scraper2.py --verbose --loops 3`
*   `--show-browser`: Run Selenium with a visible browser window (useful for debugging).
    *   Example: `python trustindex_scraper2.py --show-browser --loops 2`

## Output

The script generates two files by default (or uses the names specified via arguments):

1.  **`turkish_airlines_reviews.csv`**: A CSV file containing the scraped reviews with columns: `author`, `date`, `rating`, `body`, `source_platform`.
2.  **`turkish_airlines_reviews.xlsx`**: An Excel file with the same data in a sheet named "Reviews".

## Potential Improvements / TODO

*   Implement more sophisticated waits after clicking "More" (e.g., waiting for a specific loading element to disappear or the button to become stale).
*   Add more comprehensive error handling for network issues or unexpected page structure changes.
*   Integrate proxy rotation for larger-scale scraping to avoid IP blocks.
*   Refactor into classes for better organization if the script grows more complex.
*   Add unit tests.
*   Explore extracting additional data points if available (e.g., reviewer location, helpful votes).

## Disclaimer & Ethical Considerations

*   **Website Terms:** Always review the `robots.txt` file and Terms of Service of Trustindex.io before scraping. Ensure your scraping activities comply with their policies.
*   **Rate Limiting:** The script includes basic `time.sleep()` delays. Be mindful of the website's resources and avoid overly aggressive scraping, which could lead to IP blocks. Adjust delays as needed.
*   **Website Changes:** Web scraping scripts are often brittle. Changes to the Trustindex.io website structure or loading mechanism may break this script. Regular maintenance might be required.
*   **Data Usage:** Use the scraped data responsibly and ethically.

---

*You might want to add a LICENSE file (e.g., MIT License) if you intend for others to use or contribute to your code.*
```

**Next Steps:**

1.  **Create `requirements.txt`:** As mentioned in the README setup, run `pip freeze > requirements.txt` in your activated virtual environment to create the dependencies file.
2.  **Add and Commit:**
    ```bash
    git add README.md requirements.txt # Add the new files
    git commit -m "Add README.md and requirements.txt"
    git push origin main # Push the changes to GitHub
    ```

Now your GitHub repository will have a helpful README explaining your project!

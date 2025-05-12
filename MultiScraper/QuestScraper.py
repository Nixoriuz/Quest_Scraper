import time
import json
import traceback # For detailed error logging
import datetime # For timestamping errors
import os # For checking file existence
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, ElementClickInterceptedException
from bs4 import BeautifulSoup

# --- Configuration ---
TARGET_URL = "https://oldschool.runescape.wiki/w/RuneScape:WikiSync/Tracker"
USERNAMES_FILENAME = "usernames.json" # Input file with list of usernames
# Optional: Specify the path to your WebDriver if it's not in your system PATH
# WEBDRIVER_PATH = '/path/to/your/chromedriver' # Example for Chrome
WEBDRIVER_PATH = None # Set to None if WebDriver is in PATH
OUTPUT_FILENAME_TEMPLATE = "{username}_quest_status.json" # Template for output filename
ERROR_LOG_FILENAME = "scraping_errors.log" # File to log errors

def setup_driver():
    """Sets up the Selenium WebDriver."""
    try:
        options = webdriver.ChromeOptions()
        # --- For Debugging: Comment out the next line to watch the browser ---
        # options.add_argument('--headless') # Uncomment to run headless
        # --- End Debugging Comment ---
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # Add experimental options to potentially reduce console noise
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('--log-level=3') # Suppress most logs except fatal
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        if WEBDRIVER_PATH:
            service = webdriver.ChromeService(executable_path=WEBDRIVER_PATH, log_output=os.devnull) # Suppress service logs
            driver = webdriver.Chrome(service=service, options=options)
        else:
            # Attempt to suppress service logs when using PATH as well
            service = webdriver.ChromeService(log_output=os.devnull)
            driver = webdriver.Chrome(service=service, options=options)

        print("WebDriver setup successful.")
        return driver
    except WebDriverException as e:
        print(f"Error setting up WebDriver: {e}")
        if "permission denied" in str(e).lower():
             print("Hint: Ensure the WebDriver executable has execute permissions (chmod +x).")
        elif "executable needs to be in PATH" in str(e):
             print(f"Hint: ChromeDriver not found in PATH. Either add it to PATH or set WEBDRIVER_PATH='{'/path/to/your/chromedriver'}' in the script.")
        else:
             print("Hint: Ensure WebDriver is installed, compatible with your Chrome version, and its path is correct.")
        return None
    except Exception as e:
        log_error(f"An unexpected error occurred during WebDriver setup: {e}\n{traceback.format_exc()}")
        print(f"An unexpected error occurred during WebDriver setup: {e}")
        return None

def log_error(message):
    """Appends an error message with a timestamp to the error log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ERROR_LOG_FILENAME, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n\n") # Add extra newline for readability
    except Exception as e:
        print(f"Critical Error: Could not write to error log file '{ERROR_LOG_FILENAME}'. Error: {e}")
        print(f"Original error message: {message}")


def fetch_and_interact(driver, url, username):
    """
    Navigates to the URL, interacts with the page for a specific username,
    clicks lookup, waits for results, and returns the updated page source.
    Handles potential stale element references by re-finding elements if needed.
    """
    wait_time_long = 45
    wait_time_short = 20
    attempts = 3 # Number of attempts for interaction sequence

    for attempt in range(attempts):
        print(f"\n--- Attempt {attempt + 1}/{attempts} for user: {username} ---")
        try:
            print(f"Navigating to: {url}")
            driver.get(url)
            # No implicit wait, rely on explicit waits

            # --- Interaction Logic ---
            print(f"Finding username input using placeholder...")
            username_input_selector = (By.XPATH, "//input[@placeholder='Display name']")
            username_input = WebDriverWait(driver, wait_time_long).until(
                EC.visibility_of_element_located(username_input_selector)
            )
            print("Username input found.")

            username_input.clear()
            time.sleep(0.5)
            username_input.send_keys(username)
            time.sleep(0.5)
            # Verify input value - important!
            entered_value = username_input.get_attribute('value')
            if entered_value != username:
                 print(f"Warning: Input value '{entered_value}' does not match expected '{username}' after send_keys. Retrying...")
                 raise Exception("Username input verification failed") # Trigger retry
            print(f"Sent keys and verified: {username}")


            fetch_button_selector = (By.XPATH, "//button[contains(., 'Look up')]")
            print(f"Waiting for and clicking the 'Look up' button...")
            fetch_button = WebDriverWait(driver, wait_time_short).until(
                EC.element_to_be_clickable(fetch_button_selector)
            )
            try:
                 fetch_button.click()
                 print("Look up button clicked (standard method).")
            except ElementClickInterceptedException:
                 print("Standard click intercepted, trying JavaScript click...")
                 driver.execute_script("arguments[0].click();", fetch_button)
                 print("Look up button clicked (JavaScript method).")

            # --- Wait *after* clicking lookup ---
            results_container_selector = (By.CSS_SELECTOR, 'div.div-col')
            print(f"Waiting up to {wait_time_long}s for results container ('{results_container_selector[1]}') to be present after lookup...")
            WebDriverWait(driver, wait_time_long).until(
                 EC.presence_of_element_located(results_container_selector)
            )
            print("Results container (div.div-col) is present. Adding delay for content loading...")
            time.sleep(5) # Adjust this delay as needed
            print("Delay finished. Assuming results are loaded.")

            # If successful, return page source
            return driver.page_source

        except Exception as e:
            print(f"Error during attempt {attempt + 1} for user '{username}': {e}")
            log_error(f"Attempt {attempt + 1} failed for user '{username}'. Error: {e}\n{traceback.format_exc()}")
            if attempt < attempts - 1:
                print("Retrying...")
                time.sleep(2) # Wait before retrying
            else:
                print(f"Max attempts reached for user '{username}'. Skipping.")
                return None # Failed after all attempts

    return None # Should not be reached if loop logic is correct, but acts as fallback


def parse_data(html_content, username):
    """
    Parses the HTML content for a specific username to extract quest titles and status.
    Logs errors to a file if parsing fails.
    """
    if not html_content:
        print(f"HTML content is empty for user '{username}', cannot parse.")
        return []

    print(f"Parsing HTML content for quest status (User: {username})...")
    scraped_data = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        quest_containers = soup.find_all('div', class_='div-col')

        if not quest_containers:
            warning_msg = f"Warning (User: {username}): Could not find any quest containers with class 'div-col'. Parsing cannot proceed."
            print(warning_msg)
            log_error(warning_msg)
            return []

        print(f"Found {len(quest_containers)} quest container(s) (div.div-col) for user '{username}'. Analyzing links...")
        total_links_found = 0
        parsing_errors = 0

        for container in quest_containers:
            quest_links = container.find_all('a', href=True, title=True)
            total_links_found += len(quest_links)

            for link in quest_links:
                try:
                    href = link['href']
                    if href.startswith('/w/'):
                        qc_icon_span = link.find('span', class_='rs-qc-icon')
                        if qc_icon_span:
                            status_img = qc_icon_span.find('img')
                            if status_img:
                                status = "unknown"
                                img_classes = status_img.get('class', [])
                                if 'qc-complete' in img_classes:
                                    status = "complete"
                                elif 'qc-not-started' in img_classes:
                                    status = "not started"
                                # Add other potential statuses if needed (e.g., 'qc-in-progress')

                                quest_title = link.get('title', '').strip()
                                if not quest_title:
                                    quest_title = link.contents[0].strip() if link.contents else link.get_text(strip=True)

                                if status != "unknown":
                                     scraped_data.append({
                                         'title': quest_title,
                                         'status': status
                                     })

                except Exception as e_link:
                    parsing_errors += 1
                    error_detail = f"Error parsing individual quest link (User: {username}). Error: {e_link}\nProblematic Link HTML:\n{link.prettify()}"
                    print(f"  -> Error parsing one link for user '{username}': {e_link}. See {ERROR_LOG_FILENAME} for details.")
                    log_error(error_detail)

        print(f"Analyzed {total_links_found} potential quest links for user '{username}'.")
        if parsing_errors > 0:
            print(f"Encountered {parsing_errors} error(s) during parsing for user '{username}'. Check '{ERROR_LOG_FILENAME}'.")

        if not scraped_data and total_links_found > 0 and parsing_errors == 0:
             print(f"Warning (User: {username}): Found links, but none had recognizable status icons. Check HTML structure.")
        elif not scraped_data and total_links_found == 0:
             print(f"No quest links found within containers for user '{username}'.")

        print(f"Finished parsing for user '{username}'. Found {len(scraped_data)} quests with status.")
        return scraped_data

    except Exception as e_main:
        error_msg = f"Major error during HTML parsing for user '{username}': {e_main}"
        print(f"{error_msg}. See {ERROR_LOG_FILENAME} for details.")
        log_error(f"{error_msg}\n{traceback.format_exc()}")
        return []

def save_to_json(data, filename):
    """
    Saves the scraped data to a JSON file.
    """
    if not data:
        print(f"No data to save for {filename}.")
        return

    try:
        # Ensure directory exists if filename contains path separators (optional)
        # output_dir = os.path.dirname(filename)
        # if output_dir and not os.path.exists(output_dir):
        #     os.makedirs(output_dir)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Data successfully saved to {filename}")
    except IOError as e:
        error_msg = f"Error writing to file {filename}: {e}"
        print(error_msg)
        log_error(error_msg)
    except Exception as e:
        error_msg = f"An unexpected error occurred while saving JSON to {filename}: {e}"
        print(error_msg)
        log_error(f"{error_msg}\n{traceback.format_exc()}")

# --- Main Execution ---
if __name__ == "__main__":
    # Clear error log at the start of a run (optional)
    # with open(ERROR_LOG_FILENAME, 'w') as f: pass

    # --- Read Usernames ---
    usernames = []
    if not os.path.exists(USERNAMES_FILENAME):
        print(f"Error: Usernames file '{USERNAMES_FILENAME}' not found.")
        log_error(f"Usernames file '{USERNAMES_FILENAME}' not found.")
    else:
        try:
            with open(USERNAMES_FILENAME, 'r', encoding='utf-8') as f:
                usernames = json.load(f)
            if not isinstance(usernames, list):
                print(f"Error: Content of '{USERNAMES_FILENAME}' is not a valid JSON list.")
                log_error(f"Content of '{USERNAMES_FILENAME}' is not a valid JSON list.")
                usernames = [] # Reset to empty list
            elif not all(isinstance(u, str) for u in usernames):
                 print(f"Error: Not all items in '{USERNAMES_FILENAME}' are strings.")
                 log_error(f"Not all items in '{USERNAMES_FILENAME}' are strings.")
                 usernames = [] # Reset to empty list
            else:
                 print(f"Successfully loaded {len(usernames)} usernames from '{USERNAMES_FILENAME}'.")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from '{USERNAMES_FILENAME}': {e}")
            log_error(f"Error decoding JSON from '{USERNAMES_FILENAME}': {e}")
            usernames = []
        except Exception as e:
            print(f"Error reading usernames file '{USERNAMES_FILENAME}': {e}")
            log_error(f"Error reading usernames file '{USERNAMES_FILENAME}': {e}\n{traceback.format_exc()}")
            usernames = []

    # --- Process Usernames ---
    if not usernames:
        print("No valid usernames loaded. Exiting.")
    else:
        driver = setup_driver()
        if driver:
            try:
                for username in usernames:
                    print(f"\n{'='*10} Processing User: {username} {'='*10}")
                    # Sanitize username for filename (replace invalid characters)
                    safe_username = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in username)
                    output_file = OUTPUT_FILENAME_TEMPLATE.format(username=safe_username)

                    html_after_interaction = fetch_and_interact(driver, TARGET_URL, username)

                    if html_after_interaction:
                        extracted_data = parse_data(html_after_interaction, username)
                        save_to_json(extracted_data, output_file)
                    else:
                        print(f"Skipping data processing for user '{username}' due to fetch/interaction failure.")
                        log_error(f"Fetch/interaction failed for user '{username}'. Data processing skipped.")

                    # Optional: Add a small delay between users to be polite
                    time.sleep(2)

            except Exception as e_main_exec:
                 error_msg = f"An unexpected error occurred in the main processing loop: {e_main_exec}"
                 print(f"{error_msg}. See {ERROR_LOG_FILENAME} for details.")
                 log_error(f"{error_msg}\n{traceback.format_exc()}")
            finally:
                print("\nFinished processing all usernames.")
                print("Closing browser.")
                if driver:
                    driver.quit()
        else:
            print("WebDriver setup failed. Exiting.")


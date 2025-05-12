import time
import json
import traceback # For detailed error logging
import datetime # For timestamping errors
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, ElementClickInterceptedException
from bs4 import BeautifulSoup

# --- Configuration ---
TARGET_URL = "https://oldschool.runescape.wiki/w/RuneScape:WikiSync/Tracker"
USERNAME_TO_SELECT = "UsernameHere"
# Optional: Specify the path to your WebDriver if it's not in your system PATH
# WEBDRIVER_PATH = '/path/to/your/chromedriver' # Example for Chrome
WEBDRIVER_PATH = None # Set to None if WebDriver is in PATH
OUTPUT_FILENAME = "runescape_quest_status.json"
ERROR_LOG_FILENAME = "parsing_errors.log" # File to log parsing errors

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
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        if WEBDRIVER_PATH:
            service = webdriver.ChromeService(executable_path=WEBDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)
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
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Critical Error: Could not write to error log file '{ERROR_LOG_FILENAME}'. Error: {e}")
        print(f"Original error message: {message}")


def fetch_and_interact(driver, url, username):
    """
    Navigates to the URL, interacts with the page using corrected selectors,
    clicks lookup, waits for results, and returns the updated page source.
    """
    wait_time_long = 45
    wait_time_short = 20

    try:
        print(f"Navigating to: {url}")
        driver.get(url)
        driver.implicitly_wait(5) # General implicit wait

        # --- Interaction Logic ---
        print(f"Attempting to find username input using placeholder...")
        username_input_selector = (By.XPATH, "//input[@placeholder='Display name']")
        username_input = WebDriverWait(driver, wait_time_long).until(
            EC.visibility_of_element_located(username_input_selector)
        )
        print("Username input found.")

        username_input.clear()
        time.sleep(0.5)
        username_input.send_keys(username)
        time.sleep(0.5)
        print(f"Sent keys: {username}")

        fetch_button_selector = (By.XPATH, "//button[contains(., 'Look up')]")
        try:
            print(f"Attempting to wait for and click the 'Look up' button...")
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
            # Wait for the specific div containing the quest lists to appear
            # Using the class you provided. We wait for *any* div with this class.
            results_container_selector = (By.CSS_SELECTOR, 'div.div-col') # CORRECTED SELECTOR for results area
            print(f"Waiting up to {wait_time_long}s for results container ('{results_container_selector[1]}') to be present after lookup...")
            WebDriverWait(driver, wait_time_long).until(
                 EC.presence_of_element_located(results_container_selector)
            )
            print("Results container (div.div-col) is present. Adding delay for content loading...")
            time.sleep(5) # Adjust this delay as needed
            print("Delay finished. Assuming results are loaded.")

        except TimeoutException:
            error_msg = "Error: Timed out waiting for the 'Look up' button to be clickable."
            print(error_msg)
            log_error(error_msg)
            return None
        except Exception as e:
            error_msg = f"Error clicking 'Look up' button or waiting after click: {e}"
            print(error_msg)
            log_error(f"{error_msg}\n{traceback.format_exc()}")
            return None

        # Return the page source *after* interaction and waiting
        return driver.page_source

    except TimeoutException as e:
        error_msg = f"Error: Timed out during initial element location (e.g., username input). Wait time: {wait_time_long}s."
        print(error_msg)
        log_error(error_msg)
        return None
    except NoSuchElementException as e:
        error_msg = f"Error: Could not find a required element using the current selectors: {e}"
        print(error_msg)
        log_error(error_msg)
        return None
    except Exception as e:
        error_msg = f"An unexpected error occurred during page interaction: {e}"
        print(error_msg)
        log_error(f"{error_msg}\n{traceback.format_exc()}")
        return None

def parse_data(html_content):
    """
    Parses the HTML content to extract quest titles and their completion status.
    Logs errors to a file if parsing fails for specific items.
    """
    if not html_content:
        print("HTML content is empty, cannot parse.")
        return []

    print("Parsing HTML content for quest status...")
    scraped_data = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find all relevant containers for quests (using the class you provided)
        # There might be multiple divs with this class, find_all gets them all.
        quest_containers = soup.find_all('div', class_='div-col')
        if not quest_containers:
            warning_msg = "Warning: Could not find any quest containers with class 'div-col'. Parsing cannot proceed."
            print(warning_msg)
            log_error(warning_msg)
            # Optional: Save the HTML that failed to parse for debugging
            # with open("failed_parse_debug.html", "w", encoding="utf-8") as f:
            #     f.write(html_content)
            return []

        print(f"Found {len(quest_containers)} quest container(s) (div.div-col). Analyzing links within...")
        total_links_found = 0
        parsing_errors = 0

        # Iterate through each container found
        for container in quest_containers:
            # Find all links within this specific container
            quest_links = container.find_all('a', href=True, title=True)
            total_links_found += len(quest_links)

            for link in quest_links:
                try: # Add try/except around processing each individual link
                    href = link['href']
                    # Basic check if it looks like a quest link
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

                                quest_title = link.get('title', '').strip()
                                # Simple fallback for title if attribute missing
                                if not quest_title:
                                    quest_title = link.contents[0].strip() if link.contents else link.get_text(strip=True)


                                if status != "unknown":
                                     scraped_data.append({
                                         'title': quest_title,
                                         'status': status
                                     })
                                # else: # Optional: Log quests with unknown status if needed
                                #     log_error(f"Quest '{quest_title}' found but status icon class unknown: {img_classes}. Link: {link.prettify()}")

                except Exception as e_link:
                    # Log error for this specific link and continue with the next
                    parsing_errors += 1
                    error_detail = f"Error parsing individual quest link. Error: {e_link}\nProblematic Link HTML:\n{link.prettify()}"
                    print(f"  -> Error parsing one link: {e_link}. See {ERROR_LOG_FILENAME} for details.")
                    log_error(error_detail)
                    # Optional: Add traceback here if needed: \n{traceback.format_exc()}

        print(f"Analyzed {total_links_found} potential quest links across {len(quest_containers)} container(s).")
        if parsing_errors > 0:
            print(f"Encountered {parsing_errors} error(s) during parsing. Check '{ERROR_LOG_FILENAME}'.")

        if not scraped_data and total_links_found > 0 and parsing_errors == 0:
             print("Warning: Found links in containers, but none had recognizable status icons ('qc-complete' or 'qc-not-started'). Check HTML structure or icon classes.")
        elif not scraped_data and total_links_found == 0:
             print("No quest links found within the 'div.div-col' containers.")


        print(f"Finished parsing. Found {len(scraped_data)} quests with status.")
        return scraped_data

    except Exception as e_main:
        # Catch broader errors during soup processing or container finding
        error_msg = f"Major error during HTML parsing: {e_main}"
        print(f"{error_msg}. See {ERROR_LOG_FILENAME} for details.")
        log_error(f"{error_msg}\n{traceback.format_exc()}")
        # Optional: Save the HTML that failed to parse for debugging
        # try:
        #     with open("failed_parse_debug.html", "w", encoding="utf-8") as f:
        #         f.write(html_content)
        # except Exception as e_write:
        #     log_error(f"Could not save debug HTML file: {e_write}")
        return [] # Return empty list on major parsing failure

def save_to_json(data, filename):
    """
    Saves the scraped data to a JSON file.
    """
    if not data:
        print("No data to save.")
        return

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Data successfully saved to {filename}")
    except IOError as e:
        error_msg = f"Error writing to file {filename}: {e}"
        print(error_msg)
        log_error(error_msg)
    except Exception as e:
        error_msg = f"An unexpected error occurred while saving JSON: {e}"
        print(error_msg)
        log_error(f"{error_msg}\n{traceback.format_exc()}")

# --- Main Execution ---
if __name__ == "__main__":
    # Clear error log at the start of a run (optional)
    # with open(ERROR_LOG_FILENAME, 'w') as f: pass

    driver = setup_driver()

    if driver:
        try: # Add try...finally to ensure driver quits
            html_after_interaction = fetch_and_interact(driver, TARGET_URL, USERNAME_TO_SELECT)

            if html_after_interaction:
                # Optional: Save raw HTML for debugging parsing issues
                # with open("debug_page_source.html", "w", encoding="utf-8") as f:
                #     f.write(html_after_interaction)
                # print("Saved raw HTML to debug_page_source.html")

                extracted_data = parse_data(html_after_interaction)
                save_to_json(extracted_data, OUTPUT_FILENAME)
            else:
                print("Failed to fetch or interact with the website correctly (fetch_and_interact returned None).")

        except Exception as e_main_exec:
             # Catch any unexpected errors during the main execution flow
             error_msg = f"An unexpected error occurred in the main execution block: {e_main_exec}"
             print(f"{error_msg}. See {ERROR_LOG_FILENAME} for details.")
             log_error(f"{error_msg}\n{traceback.format_exc()}")
        finally:
            # Close the browser
            print("Closing browser.")
            if driver:
                driver.quit()
    else:
        print("WebDriver setup failed. Exiting.")


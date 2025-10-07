import os
import time
import zipfile
import mimetypes
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)

# ------------------------
# Configuration
# ------------------------
N8N_WEBHOOK_URL = "https://anasellll.app.n8n.cloud/webhook/f234915f-8cdc-4838-8bf8-c3ee74680513"
DOWNLOAD_DIR = "/home/runner/work/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

USERNAME = "contact@targetupconsulting.com"
PASSWORD = "TargetUp2024@@"

# ------------------------
# Selenium setup
# ------------------------
options = webdriver.ChromeOptions()
prefs = {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True,
}
options.add_experimental_option("prefs", prefs)
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")

service = Service("/usr/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 15)

# ------------------------
# Helper functions
# ------------------------
def zip_files(file_paths, zip_name):
    """Compress a list of files into a zip archive."""
    zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in file_paths:
            try:
                zipf.write(f, os.path.basename(f))
            except Exception as e:
                print(f"⚠️ Error adding file to ZIP: {e}")
    return zip_path


def send_zip_to_webhook(webhook_url, zip_path, payload):
    """Send ZIP file to n8n webhook."""
    try:
        with open(zip_path, "rb") as f:
            files = {"file": (os.path.basename(zip_path), f, "application/zip")}
            response = requests.post(webhook_url, data=payload, files=files)
        print(f"✅ Sent ZIP → {os.path.basename(zip_path)} (Status: {response.status_code})")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Webhook send failed: {e}")
        return False


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ------------------------
# Headless-friendly login
# ------------------------
from selenium.webdriver.common.action_chains import ActionChains

def robust_login(driver, wait, username, password):
    from datetime import datetime
    import time

    def log(msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    try:
        log("🔐 Attempting login...")

        # 1️⃣ Click the login dropdown
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".sign-in-dropdown__toggle")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
        ActionChains(driver).move_to_element(login_button).click().perform()
        log("ℹ️ Login dropdown clicked.")
        time.sleep(1)  # wait for animation

        # 2️⃣ Username input
        username_input = wait.until(EC.element_to_be_clickable((By.NAME, "username")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", username_input)
        ActionChains(driver).move_to_element(username_input).click().send_keys(username).perform()
        log("ℹ️ Username entered.")

        # 3️⃣ Password input
        password_input = wait.until(EC.element_to_be_clickable((By.NAME, "password")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", password_input)
        ActionChains(driver).move_to_element(password_input).click().send_keys(password).perform()
        log("ℹ️ Password entered.")

        # 4️⃣ Submit button
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.button-primary-blue")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
        ActionChains(driver).move_to_element(submit_button).click().perform()
        log("ℹ️ Submit button clicked.")

        continue_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Continue signing in']"))
            )
        driver.execute_script("arguments[0].click();", continue_button)
        log("➡️ Clicked 'Continue signing in'.")


        # 5️⃣ Verify login
        try:
            account_icon = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".account-user__menu-toggle")))
            log("✅ Login successful!")
        except TimeoutException:
            log("⚠️ Login may have failed: post-login element not found.")
            driver.save_screenshot("login_debug.png")
            log("💾 Screenshot saved as login_debug.png for debugging.")

    except Exception as e:
        log(f"❌ Login failed: {e}")
        driver.save_screenshot("login_debug.png")
        log("💾 Screenshot saved as login_debug.png for debugging.")


# ------------------------
# Start automation
# ------------------------
print("🚀 Starting tender collection bot...")
driver.get("https://www.developmentaid.org")

# Accept cookies
try:
    accept_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]")))
    accept_button.click()
    print("✅ Accepted cookies.")
except TimeoutException:
    print("⚠️ No cookie popup found.")
    
robust_login(driver, wait, USERNAME, PASSWORD)
# ------------------------
# Collect tender URLs
# ------------------------
today = datetime.today().strftime("%Y-%m-%d")
urls = []

print("\n🔍 Collecting tender URLs...")
for i in range(1, 2):  # You can increase later
    url = f"https://www.developmentaid.org/tenders/search?pageNr={i}&pageSize=50&postedFrom={today}"
    driver.get(url)
    time.sleep(2)
    try:
        links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "search-card__title")))
        for link in links:
            href = link.get_attribute("href")
            if href:
                urls.append(href)
        print(f"✅ Page {i}: {len(links)} tenders found.")
    except Exception as e:
        print(f"⚠️ Failed to process page {i}: {e}")

print(f"📦 Total URLs collected: {len(urls)}")
urls = urls[:5]  # Limit for testing in GitHub Actions

# ------------------------
# Process each tender
# ------------------------
for idx, tender_url in enumerate(urls, start=1):
    print(f"\n{'='*30}\n🔹 [{idx}/{len(urls)}] Processing tender: {tender_url}")
    driver.get(tender_url)
    time.sleep(2)

    files_before = set(os.listdir(DOWNLOAD_DIR))

    # Try downloading PDF
    try:
        pdf_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Download')]")))
        driver.execute_script("arguments[0].click();", pdf_button)
        print("📄 Download started.")
        time.sleep(5)
    except TimeoutException:
        print("⚠️ No job description PDF found.")

    # Check attachments
    try:
        attachments = driver.find_elements(By.CSS_SELECTOR, ".download-document")
        for a in attachments:
            try:
                driver.execute_script("arguments[0].click();", a)
                print(f"📎 Attachment download: {a.text.strip()}")
                time.sleep(2)
            except StaleElementReferenceException:
                continue
    except Exception as e:
        print(f"⚠️ Attachment issue: {e}")

    # Identify new downloads
    files_after = set(os.listdir(DOWNLOAD_DIR))
    new_files = list(files_after - files_before)
    downloaded_files = [os.path.join(DOWNLOAD_DIR, f) for f in new_files]

    if not downloaded_files:
        print("🤔 No files downloaded.")
        continue

    # Zip the files
    zip_name = f"tender_{idx}_{int(time.time())}.zip"
    zip_path = zip_files(downloaded_files, zip_name)
    print(f"📦 Zipped {len(downloaded_files)} files → {zip_name}")

    # Send to webhook
    payload = {"tender_url": tender_url, "timestamp": str(datetime.now())}
    success = send_zip_to_webhook(N8N_WEBHOOK_URL, zip_path, payload)

    # Wait for webhook acknowledgment
    if success:
        print("⏳ Waiting 5 seconds before next page...")
        time.sleep(5)
    else:
        print("❌ Webhook failed, stopping process.")
        

    # Cleanup
    for f in downloaded_files + [zip_path]:
        try:
            os.remove(f)
        except Exception:
            pass

driver.quit()
print("\n✅ Finished all tenders successfully.")

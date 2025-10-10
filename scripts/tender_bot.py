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
    StaleElementReferenceException,
    ElementClickInterceptedException
)
from selenium.webdriver.common.action_chains import ActionChains

# ------------------------
# Configuration
# ------------------------
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
# Logging helper
# ------------------------
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ------------------------
# Login
# ------------------------
def robust_login(driver, wait, username, password):
    try:
        log("🔐 Attempting login...")
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".sign-in-dropdown__toggle")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
        ActionChains(driver).move_to_element(login_button).click().perform()
        time.sleep(1)

        username_input = wait.until(EC.element_to_be_clickable((By.NAME, "username")))
        ActionChains(driver).move_to_element(username_input).click().send_keys(username).perform()

        password_input = wait.until(EC.element_to_be_clickable((By.NAME, "password")))
        ActionChains(driver).move_to_element(password_input).click().send_keys(password).perform()

        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.button-primary-blue")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
        ActionChains(driver).move_to_element(submit_button).click().perform()
        log("ℹ️ Login form submitted.")
        time.sleep(3)

        try:
            continue_btn = driver.find_element(By.XPATH, "//button[normalize-space()='Continue signing in']")
            continue_btn.click()
            log("🔁 Continued sign-in.")
        except Exception:
            pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".account-user__menu-toggle")))
        log("✅ Login successful!")

    except Exception as e:
        log(f"❌ Login failed: {e}")
        driver.save_screenshot("login_debug.png")

# ------------------------
# Webhook sender
# ------------------------
def send_zip_to_webhook(webhook_url, zip_path, payload):
    """Send ZIP file to n8n webhook and delete after sending."""
    try:
        with open(zip_path, "rb") as f:
            files = {"file": (os.path.basename(zip_path), f, "application/zip")}
            response = requests.post(webhook_url, data=payload, files=files)
        log(f"📨 Webhook response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            os.remove(zip_path)
            log(f"🧹 Deleted ZIP after successful send: {os.path.basename(zip_path)}")
            return True
        return False
    except Exception as e:
        log(f"❌ Webhook send failed: {e}")
        return False

# ------------------------
# Start automation
# ------------------------
log("🚀 Starting tender collection bot...")
driver.get("https://www.developmentaid.org")

# Accept cookies
try:
    accept_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]")))
    accept_button.click()
    log("✅ Accepted cookies.")
except TimeoutException:
    log("⚠️ No cookie popup found.")

# Perform login
robust_login(driver, wait, USERNAME, PASSWORD)

# ------------------------
# Collect tender URLs
# ------------------------
today = datetime.today().strftime("%Y-%m-%d")
urls = []

log("🔍 Collecting tender URLs...")
for i in range(1, 4):
    url = f"https://www.developmentaid.org/tenders/search?pageNr={i}&pageSize=300&postedFrom={today}"
    driver.get(url)
    time.sleep(2)
    try:
        links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "search-card__title")))
        for link in links:
            href = link.get_attribute("href")
            if href:
                urls.append(href)
        log(f"✅ Page {i}: {len(links)} tenders found.")
    except Exception as e:
        log(f"⚠️ Failed to process page {i}: {e}")

log(f"📦 Total URLs collected: {len(urls)}")
urls = urls[:5]  # limit for testing

# ------------------------
# Process each tender
# ------------------------
for idx, tender_url in enumerate(urls, start=1):
    log(f"\n{'='*30}\n🔹 [{idx}/{len(urls)}] Processing tender: {tender_url}")
    driver.get(tender_url)
    time.sleep(2)

    # --- SESSION START (Track only new downloads) ---
    session_start = datetime.now().timestamp()

    # --- STEP 1: Download main file ---
    try:
        pdf_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Download')]")))
        driver.execute_script("arguments[0].click();", pdf_button)
        log("📄 Main file download started.")
        time.sleep(5)
    except TimeoutException:
        log("⚠️ No main file found.")

    # --- STEP 2: Download attachments (ZIP or individually) ---
    try:
        download_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "da-download-entity-docs-archive .download-all")
        ))
        download_button.click()
        log("📦 Attachments ZIP download started.")
        time.sleep(8)
    except Exception as e:
        log(f"⚠️ Download all button issue: {e}")
        attachments = driver.find_elements(By.CSS_SELECTOR, ".download-document")
        for a in attachments:
            try:
                driver.execute_script("arguments[0].click();", a)
                log(f"📎 Attachment download: {a.text.strip()}")
                time.sleep(2)
            except Exception:
                continue

    # --- STEP 3: Gather session files ---
    time.sleep(5)
    files = [
        os.path.join(DOWNLOAD_DIR, f)
        for f in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))
        and os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)) >= session_start
    ]

    if not files:
        log("⚠️ No new files detected for this tender.")
        continue
    else:
        log(f"🕒 Found {len(files)} new files downloaded in this session.")

    # --- STEP 4: Merge into ZIP ---
    files = sorted(files, key=os.path.getmtime, reverse=True)
    zip_files = [f for f in files if f.lower().endswith(".zip")]
    other_files = [f for f in files if not f.lower().endswith(".zip")]

    final_zip_path = os.path.join(DOWNLOAD_DIR, f"tender_{idx}_{int(time.time())}.zip")

    if zip_files:
        zip_path = zip_files[0]
        with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zipf:
            for f in other_files:
                zipf.write(f, arcname=os.path.basename(f))
                log(f"📦 Added {os.path.basename(f)} into {os.path.basename(zip_path)}")
        os.rename(zip_path, final_zip_path)
        log(f"✅ Final merged ZIP saved at: {final_zip_path}")
    else:
        with zipfile.ZipFile(final_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for f in other_files:
                zipf.write(f, arcname=os.path.basename(f))
                log(f"🗂️ Added {os.path.basename(f)} into new ZIP.")
        log(f"✅ Created new ZIP: {final_zip_path}")

    # --- STEP 5: Send to webhook & delete ZIP ---
    payload = {"tender_url": tender_url, "timestamp": datetime.now().isoformat()}
    success = send_zip_to_webhook(WEBHOOK_URL, final_zip_path, payload)
    if success:
        log(f"🚀 Successfully sent tender {idx} → n8n")
    else:
        log(f"❌ Failed to send tender {idx} → n8n")

# ------------------------
# Cleanup
# ------------------------
driver.quit()
log("✅ Browser closed. Finished all tenders successfully.")

import os
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ------------------------
# Setup for GitHub Actions
# ------------------------
DOWNLOAD_DIR = "/home/runner/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

WEBHOOK_URL = "https://anasellll.app.n8n.cloud/webhook-test/f234915f-8cdc-4838-8bf8-c3ee74680513"

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
# Open site & login
# ------------------------
driver.get("https://www.developmentaid.org")
try:
    accept_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]"))
    )
    accept_button.click()
    print("✅ Accepted cookies.")
except TimeoutException:
    print("⚠️ Cookie popup not found or already accepted.")

try:
    print("🔐 Logging in...")
    driver.find_element(By.CSS_SELECTOR, ".sign-in-dropdown__toggle").click()
    wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys("contact@targetupconsulting.com")
    driver.find_element(By.NAME, "password").send_keys("TargetUp2024@@")
    driver.find_element(By.CSS_SELECTOR, "button.button-primary-blue").click()
    time.sleep(3)
    print("✅ Logged in successfully.")
except Exception as e:
    print(f"❌ Login failed: {e}")

# ------------------------
# Collect tender URLs
# ------------------------
# today = datetime.today().strftime("%Y-%m-%d")
today = "2025-10-05"

for page in range(1, 3):  # two pages max for testing
    print(f"\n📄 Processing page {page}...")
    page_url = f"https://www.developmentaid.org/tenders/search?pageNr={page}&pageSize=50&postedFrom={today}"
    driver.get(page_url)
    time.sleep(3)

    # Collect links
    urls = []
    try:
        links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "search-card__title")))
        for link in links:
            href = link.get_attribute("href")
            if href:
                urls.append(href)
        print(f"✅ Found {len(urls)} tenders.")
    except Exception as e:
        print(f"⚠️ Could not load page {page}: {e}")
        continue

    urls = urls[:5]
    # Visit each tender
    for idx, tender_url in enumerate(urls[:5], start=1):  # limit for testing
        print(f"🔹 [{idx}] {tender_url}")
        driver.get(tender_url)
        time.sleep(2)

        # Try PDF or attachments
        try:
            pdf_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Download')]")))
            driver.execute_script("arguments[0].click();", pdf_button)
            print("📄 Download triggered.")
        except TimeoutException:
            print("⚠️ No PDF found.")

        time.sleep(3)
        try:
            attachments = driver.find_elements(By.CSS_SELECTOR, ".download-document")
            for a in attachments:
                driver.execute_script("arguments[0].click();", a)
                time.sleep(1)
            if attachments:
                print(f"📎 {len(attachments)} attachments downloaded.")
        except Exception as e:
            print(f"⚠️ Attachments issue: {e}")

    # ------------------------
    # Send files from this page to n8n
    # ------------------------
    print(f"📤 Sending files from page {page} to webhook...")
    files = []
    for filename in os.listdir(DOWNLOAD_DIR):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.isfile(filepath):
            files.append(("files", (filename, open(filepath, "rb"))))

    if files:
        try:
            response = requests.post(WEBHOOK_URL, files=files)
            print(f"✅ Sent {len(files)} files — status: {response.status_code}")
            if response.status_code == 200:
                print("✅ n8n acknowledged, continuing...")
            else:
                print("⚠️ n8n responded with error, stopping...")
                break
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            break
        finally:
            # Close file handles and clean up folder for next page
            for _, f in files:
                f[1].close()
            for f in os.listdir(DOWNLOAD_DIR):
                os.remove(os.path.join(DOWNLOAD_DIR, f))
    else:
        print("⚠️ No files found to send.")

driver.quit()
print("🏁 All done!")

import os
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# ------------------------
# Setup for GitHub Actions
# ------------------------
DOWNLOAD_DIR = "/home/runner/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
# Open site & accept cookies
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

# ------------------------
# Log in
# ------------------------
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
today = datetime.today().strftime("%Y-%m-%d")
urls = []

for i in range(1, 2):  # fewer pages for GitHub Actions
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
urls = urls[:5]

# ------------------------
# Visit each tender & download files
# ------------------------
for idx, tender_url in enumerate(urls, start=1):
    print(f"\n🔹 [{idx}/{len(urls)}] {tender_url}")
    driver.get(tender_url)
    time.sleep(2)

    try:
        pdf_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Download')]")))
        driver.execute_script("arguments[0].click();", pdf_button)
        print("📄 Download triggered.")
    except TimeoutException:
        print("⚠️ No PDF found.")

    try:
        attachments = driver.find_elements(By.CSS_SELECTOR, ".download-document")
        for a in attachments:
            driver.execute_script("arguments[0].click();", a)
            time.sleep(1)
        if attachments:
            print(f"📎 {len(attachments)} attachments downloaded.")
    except Exception as e:
        print(f"⚠️ Attachments issue: {e}")

driver.quit()
print("✅ Done.")

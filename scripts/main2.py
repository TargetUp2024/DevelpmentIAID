import requests
import os
import pandas as pd
import fitz  # PyMuPDF
from docx import Document
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import tempfile
import time
import re # Added for text cleanup

# --------------------------------------------------
# CONFIG (GitHub Actions friendly)
# --------------------------------------------------
API_KEY = os.environ.get("API_KEY")
BASE_URL = "https://www.developmentaid.org/api/external/tenders"

HEADERS = {
    "X-API-KEY": API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

today = datetime.today().strftime("%Y-%m-%d")
yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

print("✅ Script started")
print(f"🔑 API KEY loaded: {'YES' if API_KEY else 'NO'}")
print(f"🔗 n8n WEBHOOK URL loaded: {'YES' if WEBHOOK_URL else 'NO'}")

# --------------------------------------------------
# OCR FALLBACK (PDF ONLY)
# --------------------------------------------------
def perform_pdf_ocr(file_path):
    print("    🔍 Running PDF OCR fallback...")
    try:
        images = convert_from_path(file_path)
        text = ""
        for i, img in enumerate(images):
            text += f"\n[Page {i+1}]\n"
            text += pytesseract.image_to_string(img)
        print("    ✅ PDF OCR completed")
        return text.strip()
    except Exception as e:
        print(f"    ⚠️ PDF OCR failed or missing dependencies. Skipping...")
        return ""

# --------------------------------------------------
# SMART CONTENT EXTRACTION
# --------------------------------------------------
def extract_content(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    try:
        if ext == ".pdf":
            print("    📄 Extracting PDF with Fitz")
            doc = fitz.open(file_path)
            text = " ".join(page.get_text("text") for page in doc).strip()
            doc.close()

            if text:
                print(f"    ✅ PDF text extracted ({len(text)} chars)")
            else:
                print("    ⚠️ No text layer found in PDF")
                text = perform_pdf_ocr(file_path)

        elif ext in[".png", ".jpg", ".jpeg"]:
            print(f"    🖼️ Running OCR on Image ({ext})")
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img).strip()
            print(f"    ✅ Image OCR completed ({len(text)} chars)")

        elif ext == ".docx":
            print("    📝 Extracting DOCX")
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs).strip()
            print(f"    ✅ DOCX extracted ({len(text)} chars)")

        elif ext in [".txt", ".csv"]:
            print("    📄 Reading TXT/CSV")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

        elif ext == ".xml":
            print("    📄 Extracting XML")
            tree = ET.parse(file_path)
            text = ET.tostring(tree.getroot(), encoding="unicode", method="text").strip()
            
        else:
            print(f"    ⚠️ Unsupported file extension: {ext}. Skipping...")

    except Exception as e:
        print(f"    ❌ Extraction error: {e}. Skipping...")
        text = ""

    return text

# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------
def run_pipeline():
    print("🔎 Searching tenders...")

    search_payload = {
        "page": 1,
        "size": 10,
        "sort": "posted_date.desc",
        "filter": {
            "locations": [3],
            "postedFrom": yesterday
        }
    }

    res = requests.post(f"{BASE_URL}/search", json=search_payload, headers=HEADERS)
    res.raise_for_status()

    items = res.json().get("items",[])
    print(f"📦 Tenders found: {len(items)}")

    main_rows =[]
    extracted_rows =[]

    deadline_threshold = datetime.now() + timedelta(days=7)
    print(f"⏱ Deadline threshold: {deadline_threshold.date()}")

    for i, item in enumerate(items, 1):
        print(f"\n➡️ Tender {i}/{len(items)}")

        deadline_str = item.get("deadline")
        
        # FIX 1: Allow offers without deadlines to process
        if not deadline_str:
            print("   ⚠️ No deadline. Will process anyway.")
            deadline_str = "Not Specified"
        else:
            deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
            if deadline_dt <= deadline_threshold:
                print(f"   ⛔ Deadline too close ({deadline_str}), skipped")
                continue

        tender_id = item.get("id")
        title = item.get("name") 
        
        print(f"   🆔 Tender ID: {tender_id}")

        details_res = requests.get(f"{BASE_URL}/{tender_id}", headers=HEADERS)
        details = details_res.json() if details_res.status_code == 200 else {}
        
        link = details.get("url") or f"https://www.developmentaid.org/tenders/view/{tender_id}"

        print(f"   🏷️ Title: {title[:40]}..." if title else "   🏷️ Title: None")
        print(f"   🔗 Link: {link}")

        main_rows.append({
            "tender_id": tender_id,
            "title": title,  
            "deadline": deadline_str,
            "link": link      
        })

        documents = details.get("documents",[])
        print(f"   📎 Documents found: {len(documents)}")

        for doc in documents:
            doc_id = doc.get("id")
            file_name = doc.get("name")
            print(f"   ⬇️ Downloading: {file_name}")

            bin_headers = HEADERS.copy()
            bin_headers["Accept"] = "application/octet-stream"

            file_res = requests.get(f"{BASE_URL}/{tender_id}/documents/{doc_id}", headers=bin_headers)
            
            if file_res.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
                    tmp.write(file_res.content)
                    tmp_path = tmp.name

                text = extract_content(tmp_path)
                os.remove(tmp_path)
                print(f"   🧹 Temp file deleted")

                if text:
                    formatted_text = f"=== File: {file_name} ===\n{text}\n"
                    extracted_rows.append({
                        "tender_id": tender_id,
                        "formatted_text": formatted_text
                    })
                else:
                    print(f"   ⚠️ No readable text obtained from {file_name}")
            else:
                print(f"   ❌ Failed to download {file_name}")

    print("\n📊 Building final DataFrame...")

    df_main = pd.DataFrame(main_rows)
    df_text = pd.DataFrame(extracted_rows)

    if not df_text.empty:
        df_merged_text = df_text.groupby("tender_id")["formatted_text"].apply(lambda x: "\n".join(x)).reset_index()
        df_merged_text.rename(columns={"formatted_text": "text"}, inplace=True)
        final_df = df_main.merge(df_merged_text, on="tender_id", how="left")
    else:
        final_df = df_main.copy()
        if not final_df.empty:
            final_df["text"] = None

    print("✅ Pipeline finished successfully")
    return final_df


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------
if __name__ == "__main__":
    final_df = run_pipeline()
    
    if final_df.empty:
        print("\n⚠️ No tenders processed. Exiting.")
        exit()

    print(f"\n📦 Total rows to send to n8n: {len(final_df)}")

    # Ensure webhook is provided before trying to send
    if not WEBHOOK_URL:
        print("❌ CRITICAL: N8N_WEBHOOK_URL environment variable is missing!")
        exit(1)

    # Loop through each row in the DataFrame to send to n8n
    for idx, row in final_df.iterrows():
        
        extracted_text = row.get("text")
        
        # Safely handle missing text
        if pd.isna(extracted_text) or not str(extracted_text).strip():
            extracted_text = "No attachments or text extracted."
        else:
            # FIX 2: Clean up messy text (removes huge blocks of empty newlines)
            extracted_text = re.sub(r'\n+', '\n', str(extracted_text)).strip()
            
            # FIX 3: TRUNCATE text to prevent n8n "Payload Too Large" crash
            # limits text to ~5,000 characters
            MAX_CHARS = 5000
            if len(extracted_text) > MAX_CHARS:
                extracted_text = extracted_text[:MAX_CHARS] + "\n\n... [TEXT TRUNCATED BECAUSE IT WAS TOO LONG] ..."
            
        payload = {
            "title": row["title"],
            "url": row["link"],
            "deadline": row['deadline'],
            "attachments": extracted_text
        }

        print(f"\n🚀 Sending tender '{row['title'][:30]}...' ({idx+1}/{len(final_df)}) to n8n...")
        
        try:
            response = requests.post(WEBHOOK_URL, json=payload)
            
            if response.status_code == 200:
                print(f"✅ Row {idx+1} successfully sent to n8n.")
            else:
                print(f"❌ Row {idx+1} failed with status code: {response.status_code}")
                print(f"   Reason: {response.text}")
            
            # Pause to not overwhelm n8n limits
            time.sleep(2) 

        except Exception as e:
            print(f"❌ Error sending row {idx+1}: {e}")

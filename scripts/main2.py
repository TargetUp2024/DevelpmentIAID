import requests
import os
import pandas as pd
import fitz  # PyMuPDF
from docx import Document
import pytesseract
from pdf2image import convert_from_path
from PIL import Image  # Required for Image OCR
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import tempfile

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
        print(f"    ⚠️ PDF OCR failed or missing dependencies (Poppler/Tesseract). Skipping document...")
        return ""  # Return empty string to continue gracefully

# --------------------------------------------------
# SMART CONTENT EXTRACTION
# --------------------------------------------------
def extract_content(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    try:
        # -------- PDF --------
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

        # -------- IMAGES (PNG, JPG, JPEG) --------
        elif ext in [".png", ".jpg", ".jpeg"]:
            print(f"    🖼️ Running OCR on Image ({ext})")
            try:
                img = Image.open(file_path)
                text = pytesseract.image_to_string(img).strip()
                print(f"    ✅ Image OCR completed ({len(text)} chars)")
            except Exception as e:
                print(f"    ⚠️ Image OCR failed or Tesseract missing. Skipping document...")
                text = "" # Return empty string to continue gracefully

        # -------- DOCX --------
        elif ext == ".docx":
            print("    📝 Extracting DOCX")
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs).strip()
            print(f"    ✅ DOCX extracted ({len(text)} chars)")

        # -------- TXT / CSV --------
        elif ext in [".txt", ".csv"]:
            print("    📄 Reading TXT/CSV")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

        # -------- XML --------
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
        if not deadline_str:
            print("   ⚠️ No deadline, skipped")
            continue

        deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
        if deadline_dt <= deadline_threshold:
            print(f"   ⛔ Deadline too close ({deadline_str}), skipped")
            continue

        tender_id = item.get("id")
        title = item.get("name") 
        
        print(f"   🆔 Tender ID: {tender_id}")

        # Fetch Detailed info
        details_res = requests.get(f"{BASE_URL}/{tender_id}", headers=HEADERS)
        details = details_res.json() if details_res.status_code == 200 else {}
        
        link = details.get("url") or f"https://www.developmentaid.org/tenders/view/{tender_id}"

        print(f"   🏷️ Title: {title[:40]}..." if title else "   🏷️ Title: None")
        print(f"   🔗 Link: {link}")

        # Append to our main rows (Notice: reference is removed)
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

            file_res = requests.get(
                f"{BASE_URL}/{tender_id}/documents/{doc_id}",
                headers=bin_headers
            )
            
            if file_res.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
                    tmp.write(file_res.content)
                    tmp_path = tmp.name

                text = extract_content(tmp_path)
                os.remove(tmp_path)
                print(f"   🧹 Temp file deleted")

                # Only append if we actually extracted something
                if text:
                    # Format text with file name header
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
        # Group by tender_id and join all documents' formatted texts together
        df_merged_text = df_text.groupby("tender_id")["formatted_text"].apply(
            lambda x: "\n".join(x)
        ).reset_index()
        
        # Rename the column back to "text"
        df_merged_text.rename(columns={"formatted_text": "text"}, inplace=True)
        
        final_df = df_main.merge(df_merged_text, on="tender_id", how="left")
    else:
        final_df = df_main.copy()
        final_df["text"] = None

    print("✅ Pipeline finished successfully")
    return final_df

# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------
if __name__ == "__main__":
    final_df = run_pipeline()
    print("\n📄 FINAL DF PREVIEW:")
    #print(final_df.head())
    print(f"\n📦 Total rows: {len(final_df)}")



# Loop through each row in the DataFrame
for idx, row in final_df.iterrows():
    payload = {
        "title": row["title"],
        "url": row["link"],
        "deadline" : row['deadline'],
        "attachments": row["text"]
    }

    print(f"\n🚀 Sending row {idx+1}/{len(df)} to n8n...")
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        
        if response.status_code == 200:
            print(f"✅ Row {idx+1} successfully sent and acknowledged by n8n.")
        else:
            print(f"❌ Row {idx+1} failed with status code: {response.status_code}")
            print(response.text)
            time.sleep(2)

    except Exception as e:
        print(f"❌ Error sending row {idx+1}: {e}")

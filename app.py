import streamlit as st
import pandas as pd
import httpx
import re
import io
import whois
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

st.set_page_config(page_title="FunnelStrike Email Extractor", layout="centered")

# Convert Google Sheet link to CSV export link
def convert_to_csv_link(sheet_url):
    if "docs.google.com" in sheet_url and "/d/" in sheet_url:
        sheet_id = sheet_url.split("/d/")[1].split("/")[0]
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return None

# Fetch data from Google Sheet
def load_google_sheet(sheet_url):
    csv_url = convert_to_csv_link(sheet_url)
    if not csv_url:
        return None, "Invalid Google Sheet URL"
    
    try:
        df = pd.read_csv(csv_url)
        return df, None
    except Exception as e:
        return None, f"Error loading Google Sheet: {e}"

# Extract emails using regex
def extract_emails(text):
    return set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))

# Extract emails from website including 'mailto:' links
def extract_emails_from_website(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    emails = set()
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        emails.update(extract_emails(response.text))
        metadata_emails = extract_emails(str(soup.find_all("meta")))
        emails.update(metadata_emails)
        for mailto in soup.select("a[href^=mailto]"):
            emails.add(mailto["href"].replace("mailto:", ""))
        return emails
    except Exception:
        return set()

# Extract emails from WHOIS data
def extract_emails_from_whois(domain):
    try:
        w = whois.whois(domain)
        return extract_emails(str(w))
    except Exception:
        return set()

# Use Selenium to extract emails from JavaScript-heavy websites
def extract_emails_with_selenium(url):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(5)
    page_source = driver.page_source
    driver.quit()
    return extract_emails(page_source)

# Extract emails from important subpages
def extract_emails_from_subpages(url):
    subpages = ["contact", "about", "team"]
    emails = set()
    for sub in subpages:
        sub_url = urljoin(url, sub)
        emails.update(extract_emails_from_website(sub_url))
    return emails

# Main UI
st.title("FunnelStrike's Email Extractor")
st.write("Paste your **Google Sheet link** (must have a 'Website' column):")

sheet_url = st.text_input("Google Sheet URL")

if sheet_url:
    df, error = load_google_sheet(sheet_url)
    
    if error:
        st.error(error)
    elif "Website" not in df.columns:
        st.error("❌ The Google Sheet must contain a 'Website' column!")
    else:
        websites = df["Website"].dropna().tolist()
        st.success(f"✅ Loaded {len(websites)} websites")

        if st.button("Find Emails"):
            results = []
            total_emails_extracted = 0
            progress_bar = st.progress(0)
            progress_text = st.empty()

            for idx, website in enumerate(websites):
                domain = website.replace("https://", "").replace("http://", "").split("/")[0]
                emails = (extract_emails_from_website(website) |
                          extract_emails_from_subpages(website) |
                          extract_emails_with_selenium(website) |
                          extract_emails_from_whois(domain))
                
                email_count = len(emails)
                total_emails_extracted += email_count
                results.append({"Website": website, "Emails": ", ".join(emails)})
                
                percent_done = int(((idx + 1) / len(websites)) * 100)
                progress_text.text(f"Processing {idx+1}/{len(websites)} ({percent_done}%) - Emails Found: {total_emails_extracted}")
                progress_bar.progress((idx + 1) / len(websites))
            
            st.success(f"✅ Extraction Complete! Total Emails Extracted: {total_emails_extracted}")
            results_df = pd.DataFrame(results)
            st.dataframe(results_df, height=300)

            csv_buffer = io.StringIO()
            results_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv_buffer.getvalue(),
                file_name="extracted_emails.csv",
                mime="text/csv"
            )
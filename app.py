import streamlit as st
import pandas as pd
import httpx
import re
import io
import time
import threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

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

# Timer-controlled email extraction with strict timeout
def extract_emails_with_timeout(url, time_limit=60):
    emails_found = set()
    headers = {"User-Agent": "Mozilla/5.0"}
    domain = urlparse(url).netloc
    start_time = time.time()

    def fetch_emails():
        nonlocal emails_found
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                soup = BeautifulSoup(response.text, "html.parser")

                # Extract emails from page content
                emails_found.update(extract_emails(response.text))
                emails_found.update(extract_emails(str(soup.find_all("meta"))))
                emails_found.update(extract_emails(" ".join([str(s) for s in soup.find_all("script")])))

                # Extract emails from mailto links
                emails_found.update(extract_emails(" ".join([a["href"] for a in soup.find_all("a", href=True) if "mailto:" in a["href"]])))

                # Find internal links (limit to 5 links for efficiency)
                internal_links = list(set(
                    urljoin(url, a["href"]) for a in soup.find_all("a", href=True)
                    if urlparse(a["href"]).netloc == domain
                ))[:5]

                for link in internal_links:
                    if time.time() - start_time > time_limit:
                        break  # Stop processing if time exceeded
                    try:
                        response = client.get(link, headers=headers, timeout=10)
                        emails_found.update(extract_emails(response.text))
                    except httpx.TimeoutException:
                        st.warning(f"⏳ Timeout on {link}, skipping...")
                    except Exception:
                        pass  # Ignore broken links
        except httpx.TimeoutException:
            st.warning(f"⏳ Timeout on {url}, skipping...")
        except Exception as e:
            st.error(f"Error fetching {url}: {e}")

    # Run fetch_emails in a separate thread with a hard timeout
    email_thread = threading.Thread(target=fetch_emails, daemon=True)
    email_thread.start()
    email_thread.join(timeout=time_limit)  # Stop thread after time_limit

    return emails_found


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
            time_text = st.empty()

            start_overall_time = time.time()

            for idx, website in enumerate(websites):
                start_time = time.time()
                emails = extract_emails_with_timeout(website, time_limit=60)  # 1 min max per website
                
                # If timeout, show warning
                if time.time() - start_time >= 60:
                    st.warning(f"⚠️ Skipped {website} (took too long)")

                email_count = len(emails)
                total_emails_extracted += email_count
                results.append({"Website": website, "Emails": ", ".join(emails)})

                # Estimate remaining time
                elapsed_time = time.time() - start_overall_time
                estimated_time_per_website = elapsed_time / (idx + 1)
                time_remaining = estimated_time_per_website * (len(websites) - (idx + 1))

                # Update UI
                percent_done = int(((idx + 1) / len(websites)) * 100)
                progress_text.text(f"Processing {idx+1}/{len(websites)} ({percent_done}%) - Emails Found: {total_emails_extracted}")
                time_text.text(f"⏳ Estimated Time Remaining: {int(time_remaining // 60)} min {int(time_remaining % 60)} sec")
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

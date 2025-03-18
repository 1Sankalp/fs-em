import streamlit as st
import pandas as pd
import httpx
import re

st.set_page_config(page_title="Email Extractor", layout="centered")

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

# Extract emails from website
def extract_emails_from_website(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True, headers=headers)
        emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", response.text))
        return ", ".join(emails) if emails else ""
    except:
        return ""

# UI
st.title("Email Extractor from Websites")
st.write("Paste your **Google Sheet link** (it must have a 'Website' column):")

# Input field for Google Sheet link
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

        # Button to start extraction
        if st.button("Find Emails"):
            results = []
            total_emails_extracted = 0
            progress_bar = st.progress(0)
            progress_text = st.empty()  # Placeholder for dynamic text updates

            for idx, website in enumerate(websites):
                emails = extract_emails_from_website(website)
                email_count = len(emails.split(", ")) if emails else 0
                total_emails_extracted += email_count

                results.append({"Website": website, "Emails": emails})

                # Update progress
                percent_done = int(((idx + 1) / len(websites)) * 100)
                progress_text.text(f"Processing {idx+1}/{len(websites)} ({percent_done}%) - Emails Found: {total_emails_extracted}")
                progress_bar.progress((idx + 1) / len(websites))

            st.success(f"✅ Extraction Complete! Total Emails Extracted: {total_emails_extracted}")

            # Convert to DataFrame
            results_df = pd.DataFrame(results)

            # Display results in scrollable container
            st.dataframe(results_df, height=300)

            # Convert to tab-separated values (works well in Google Sheets)
            output_str = "Website\tEmails\n" + "\n".join(
                [f"{row['Website']}\t{row['Emails']}" for _, row in results_df.iterrows()]
            )

            # Create a hidden text area for copying data (Streamlit workaround)
            st.text_area("Copy the data below:", output_str, height=150)

            # Copy to clipboard button (New approach)
            st.markdown(
                f"""
                <button id="copy_btn" style="padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; border-radius: 5px;">
                    📋 Copy to Clipboard
                </button>
                <p id="copy_status" style="color: green; display: none;">✅ Copied!</p>
                
                <script>
                document.getElementById("copy_btn").addEventListener("click", function() {{
                    var textArea = document.createElement("textarea");
                    textArea.value = `{output_str}`;
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand("copy");
                    document.body.removeChild(textArea);
                    
                    document.getElementById("copy_status").style.display = "block";
                    setTimeout(() => {{
                        document.getElementById("copy_status").style.display = "none";
                    }}, 2000);
                }});
                </script>
                """,
                unsafe_allow_html=True
            )

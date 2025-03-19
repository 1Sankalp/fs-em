import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import pyperclip
from io import StringIO
from urllib.parse import urlparse

st.set_page_config(page_title="Website Email Extractor", layout="wide")

def extract_domain(url):
    """Extract domain from URL"""
    try:
        parsed_uri = urlparse(url)
        if not parsed_uri.scheme:
            url = 'http://' + url
            parsed_uri = urlparse(url)
        domain = '{uri.netloc}'.format(uri=parsed_uri)
        return domain
    except:
        return url

def extract_emails(url):
    """Extract emails from a website"""
    emails = []
    try:
        # Add http:// if not present
        if not url.startswith('http'):
            url = 'http://' + url
            
        # Request website content
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Find emails using regex
        if response.status_code == 200:
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract from text content
            text_content = soup.get_text()
            found_emails = re.findall(email_pattern, text_content)
            
            # Extract from mailto links
            mailto_links = soup.select('a[href^="mailto:"]')
            for link in mailto_links:
                href = link.get('href')
                email = href.replace('mailto:', '').split('?')[0]
                if re.match(email_pattern, email):
                    found_emails.append(email)
            
            # Remove duplicates and clean
            emails = list(set(found_emails))
    except Exception as e:
        st.error(f"Error processing {url}: {str(e)}")
        return []
    
    return emails

def get_dataframe_from_gsheet_url(sheet_url):
    """Extract data from Google Sheets URL"""
    try:
        # Convert to CSV export URL
        if "spreadsheets/d/" in sheet_url:
            sheet_id = sheet_url.split('spreadsheets/d/')[1].split('/')[0]
            export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            
            # Download the CSV data
            response = requests.get(export_url)
            if response.status_code == 200:
                data = StringIO(response.content.decode('utf-8'))
                df = pd.read_csv(data)
                return df, None
            else:
                return None, f"Failed to access sheet: HTTP {response.status_code}"
        else:
            return None, "Invalid Google Sheets URL"
    except Exception as e:
        return None, f"Error processing sheet: {str(e)}"

# Custom CSS for the scrollable container
st.markdown("""
    <style>
    .scrollable-container {
        height: 400px;
        overflow-y: auto;
        border: 1px solid #ccc;
        border-radius: 5px;
        padding: 10px;
    }
    .stButton button {
        width: 50%;
    }
    </style>
""", unsafe_allow_html=True)

# App title and description
st.title("Website Email Extractor")
st.markdown("Extract emails from websites listed in your Google Sheet")

# Input for Google Sheet URL
sheet_url = st.text_input("Enter Google Sheet URL (must be publicly accessible)")

# Column selection
website_column = None
if sheet_url:
    df, error = get_dataframe_from_gsheet_url(sheet_url)
    if error:
        st.error(error)
    elif df is not None:
        st.success("Sheet loaded successfully!")
        
        # Show column selection dropdown
        columns = df.columns.tolist()
        website_column = st.selectbox("Select the column containing website URLs", columns)

# Button to start extraction
if website_column and st.button("Find Emails"):
    # Create a container for the results
    results_container = st.container()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Extract website column and prepare results
    websites = df[website_column].tolist()
    total_sites = len(websites)
    
    # Initialize results dataframe
    results_df = pd.DataFrame(columns=["Website", "Emails"])
    
    # Process each website
    for i, website in enumerate(websites):
        if pd.notna(website) and website.strip() != "":
            status_text.text(f"Processing {i+1}/{total_sites}: {website}")
            
            # Clean up URL if needed
            clean_url = website.strip()
            domain = extract_domain(clean_url)
            
            # Extract emails
            emails = extract_emails(clean_url)
            
            # Add to results
            results_df.loc[len(results_df)] = {
                "Website": clean_url,
                "Emails": ", ".join(emails) if emails else "No emails found"
            }
            
            # Update progress
            progress_bar.progress((i + 1) / total_sites)
            time.sleep(0.1)  # Small delay to show progress
    
    # Show completion message
    status_text.text(f"Completed! Processed {total_sites} websites.")
    
    # Display results in a scrollable container
    with results_container:
        st.subheader("Extraction Results")
        
        if not results_df.empty:
            # Format the dataframe for display
            display_df = results_df.copy()
            
            # Create hyperlinks for websites
            display_df["Website"] = display_df["Website"].apply(
                lambda x: f'<a href="{x if x.startswith("http") else "http://" + x}" target="_blank">{x}</a>'
            )
            
            # Display in scrollable container with HTML
            st.markdown('<div class="scrollable-container">', unsafe_allow_html=True)
            st.write(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Create a copy button
            if st.button("Copy to Clipboard"):
                # Format for clipboard (ensure URLs are properly formatted)
                clipboard_text = ""
                for _, row in results_df.iterrows():
                    clipboard_text += f"{row['Website']}\t{row['Emails']}\n"
                
                # Use JavaScript to copy to clipboard
                st.markdown(
                    f"""
                    <script>
                    const textToCopy = `{clipboard_text}`;
                    navigator.clipboard.writeText(textToCopy)
                        .then(() => console.log('Copied to clipboard'))
                        .catch(err => console.error('Error copying text: ', err));
                    </script>
                    """,
                    unsafe_allow_html=True
                )
                
                st.success("Results copied to clipboard! Paste it into your Google Sheet.")
        else:
            st.warning("No results found. Check if the website URLs are valid.")

# Instructions at the bottom
st.markdown("---")
st.markdown("""
### Instructions:
1. Make sure your Google Sheet is publicly accessible (set to "Anyone with the link can view")
2. Paste the Google Sheet URL above
3. Select the column containing website URLs
4. Click "Find Emails" to start extraction
5. Use the "Copy to Clipboard" button to copy results for pasting into your sheet
""")
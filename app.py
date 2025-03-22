import streamlit as st
import pandas as pd
import requests
import re
import time
import json
from bs4 import BeautifulSoup
from urllib.parse import unquote, urljoin
import tldextract
from difflib import SequenceMatcher

IGNORE_DOMAINS = ["wix.com", "domain.com", "example.com", "sentry.io", "wixpress.com", "squarespace.com", "wordpress.com", "shopify.com"]

COMMON_EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com", 
                        "protonmail.com", "mail.com", "zoho.com", "yandex.com", "gmx.com"]
CONTACT_PAGES = ["/contact", "/contact-us", "/contact.html", "/contact-us.html", "/about", "/about-us", 
                "/about.html", "/about-us.html", "/get-in-touch", "/reach-us", "/connect", "/reach-out",
                "/our-team", "/team", "/support", "/help", "/info"]

# Function to validate and clean email addresses
def validate_email(email):
    # Clean and validate the email format
    email = email.strip().lower()
    
    # Ignore image files and other non-email strings containing @ symbol
    if any(ext in email for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"]):
        return None
    
    # Remove any invalid start/end characters
    email = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9\.]+$', '', email)
    
    # Check if the email follows a valid pattern
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        # Ensure the email doesn't contain file extensions or other non-email patterns
        parts = email.split('@')
        if len(parts) == 2 and "." in parts[1]:
            domain_part = parts[1]
            # Check if the domain part looks valid (not an image or file name)
            if not re.search(r'\d+x\d+', domain_part):  # Pattern often found in image dimensions
                return email
    return None

# Extract domain from URL
def get_domain(url):
    try:
        extracted = tldextract.extract(url)
        return f"{extracted.domain}.{extracted.suffix}"
    except:
        return None

# Function to clean and deduplicate emails
def clean_and_deduplicate_emails(emails_list):
    if not emails_list:
        return []
    
    # First round of cleaning and deduplication
    clean_emails = set()
    for email in emails_list:
        valid_email = validate_email(email)
        if valid_email:
            # Skip emails from the ignore domains
            if not any(ignore_domain in valid_email for ignore_domain in IGNORE_DOMAINS):
                clean_emails.add(valid_email)
    
    # Handle cases where one email is contained within another
    # (like "501-3362hello@snovistudios.com" vs "hello@snovistudios.com")
    emails_to_remove = set()
    final_emails = list(clean_emails)
    
    for i in range(len(final_emails)):
        for j in range(len(final_emails)):
            if i != j and final_emails[i] != final_emails[j]:
                # Split emails into username and domain parts
                email1_parts = final_emails[i].split('@')
                email2_parts = final_emails[j].split('@')
                
                # Check if they have the same domain
                if len(email1_parts) == 2 and len(email2_parts) == 2 and email1_parts[1] == email2_parts[1]:
                    username1 = email1_parts[0]
                    username2 = email2_parts[0]
                    
                    # If one username is contained within the other
                    if username1 in username2:
                        # Keep the shorter one (assuming it's cleaner)
                        emails_to_remove.add(final_emails[j])
                    elif username2 in username1:
                        emails_to_remove.add(final_emails[i])
                    # Special case for project.info@ vs info@
                    elif '.' in username1 and username1.split('.')[-1] == username2:
                        emails_to_remove.add(final_emails[i])
                    elif '.' in username2 and username2.split('.')[-1] == username1:
                        emails_to_remove.add(final_emails[j])
    
    # Remove emails flagged for removal
    final_cleaned = [email for email in final_emails if email not in emails_to_remove]
    
    return final_cleaned

# Function to extract emails from a website using multiple methods
def extract_emails(base_url):
    emails_set = set()  # Use set to store unique emails (case insensitive)
    domain = get_domain(base_url)
    
    # Function to process a single URL and extract emails
    def process_url(url, is_contact_page=False):
        local_emails = set()
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            response = requests.get(url, headers=headers, timeout=15)
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Method 1: Extract emails from visible text
            text_content = soup.get_text(separator=" ")
            text_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text_content)
            
            # Method 2: Extract emails from mailto links - improved
            # Find all a tags and look deeply through attributes
            all_a_tags = soup.find_all("a")
            mailto_emails = []
            for a_tag in all_a_tags:
                # Check href attribute
                href = a_tag.get("href", "")
                if "mailto:" in href:
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    email = unquote(email)  # Handle URL encoded characters
                    mailto_emails.append(email)
                
                # Also check other attributes and text for emails
                for attr_name, attr_value in a_tag.attrs.items():
                    if isinstance(attr_value, str) and "@" in attr_value:
                        potential_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", attr_value)
                        mailto_emails.extend(potential_emails)
            
            # Method 3: Check for elements with email-related classes or IDs
            email_classes = ["email", "mail", "e-mail", "contact", "email-address", "mail-link", "mini-contacts", 
                             "footer-contact", "header-contact", "contact-info", "contact-details", "contact-email",
                             "footer-email", "header-email", "info"]
            class_emails = []
            for class_name in email_classes:
                elements = soup.find_all(class_=re.compile(class_name, re.I))
                for element in elements:
                    # Extract email from text content
                    element_text = element.get_text()
                    found_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", element_text)
                    class_emails.extend(found_emails)
                    
                    # Also check attributes
                    for attr_name, attr_value in element.attrs.items():
                        if isinstance(attr_value, str) and "@" in attr_value:
                            potential_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", attr_value)
                            class_emails.extend(potential_emails)
            
            # Method 4: Extract from all tags and attributes (comprehensive scan)
            all_tags_emails = []
            for tag in soup.find_all():
                # Check tag content
                if tag.string and "@" in tag.string:
                    found_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", tag.string)
                    all_tags_emails.extend(found_emails)
                
                # Check all attributes
                for attr_name, attr_value in tag.attrs.items():
                    if isinstance(attr_value, str) and "@" in attr_value:
                        found_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", attr_value)
                        all_tags_emails.extend(found_emails)
            
            # Method 5: Extract from script tags more thoroughly
            script_emails = []
            script_tags = soup.find_all("script")
            for script in script_tags:
                if script.string:
                    # Look for explicit email field in JSON
                    email_patterns = [
                        r'"email"\s*:\s*"([^"]+@[^"]+\.[^"]+)"',       # "email": "example@domain.com"
                        r'"emailAddress"\s*:\s*"([^"]+@[^"]+\.[^"]+)"', # "emailAddress": "example@domain.com"
                        r'"mail"\s*:\s*"([^"]+@[^"]+\.[^"]+)"',         # "mail": "example@domain.com"
                        r'"e-mail"\s*:\s*"([^"]+@[^"]+\.[^"]+)"',       # "e-mail": "example@domain.com"
                        r'"contactEmail"\s*:\s*"([^"]+@[^"]+\.[^"]+)"', # "contactEmail": "example@domain.com"
                        r'"support_email"\s*:\s*"([^"]+@[^"]+\.[^"]+)"' # "support_email": "example@domain.com"
                    ]
                    
                    for pattern in email_patterns:
                        found_emails = re.findall(pattern, script.string)
                        script_emails.extend(found_emails)
                    
                    # Also extract general email pattern
                    general_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", script.string)
                    script_emails.extend(general_emails)
                    
                    # Try to parse JSON data
                    try:
                        # Extract any JSON-like structures from the script
                        json_matches = re.findall(r'\{[^{}]*\}', script.string)
                        for json_str in json_matches:
                            try:
                                data = json.loads(json_str)
                                # Recursively search for email keys in the JSON
                                def extract_json_emails(obj):
                                    found = []
                                    if isinstance(obj, dict):
                                        for key, value in obj.items():
                                            if isinstance(value, str) and any(k in key.lower() for k in ['email', 'mail', 'contact']):
                                                if '@' in value and '.' in value:
                                                    found.append(value)
                                            elif isinstance(value, (dict, list)):
                                                found.extend(extract_json_emails(value))
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            found.extend(extract_json_emails(item))
                                    return found
                                
                                json_emails = extract_json_emails(data)
                                script_emails.extend(json_emails)
                            except:
                                pass
                    except:
                        pass
            
            # Method 6: Extract from meta tags
            meta_emails = []
            meta_tags = soup.find_all("meta")
            for meta in meta_tags:
                content = meta.get("content", "")
                if "@" in content:
                    found_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content)
                    meta_emails.extend(found_emails)
            
            # Method 7: Look specifically for common email domains in the entire HTML content
            domain_based_emails = []
            for email_domain in COMMON_EMAIL_DOMAINS:
                # Find all text containing common email domains
                domain_pattern = r'[a-zA-Z0-9._%+-]+@' + re.escape(email_domain)
                found_domain_emails = re.findall(domain_pattern, html_content)
                domain_based_emails.extend(found_domain_emails)
            
            # Method 8: Look for obfuscated emails (especially on contact pages)
            if is_contact_page:
                # Look for JavaScript email obfuscation
                for script in script_tags:
                    if script.string and any(term in script.string.lower() for term in ['email', 'mail', 'contact']):
                        # Check for string concatenation
                        concat_patterns = [
                            r'[\'"]\s*\+\s*[\'"]',  # "+" patterns like 'user' + '@' + 'domain.com'
                            r'\.join\(',            # Array.join() method
                            r'\.reverse\(',         # String or array reverse()
                            r'String\.fromCharCode' # Character code conversion
                        ]
                        
                        if any(re.search(pattern, script.string) for pattern in concat_patterns):
                            # Extract anything that looks like it could be part of email when concatenated
                            parts = re.findall(r'[\'"]([a-zA-Z0-9._%+-@]+)[\'"]', script.string)
                            if parts and '@' in ''.join(parts):
                                # Try simple reconstruction for common patterns
                                reconstructed = ''.join(parts)
                                potential_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", reconstructed)
                                if potential_emails:
                                    domain_based_emails.extend(potential_emails)
                
                # Look for emails in contact form HTML structure
                contact_forms = soup.find_all('form')
                for form in contact_forms:
                    # Check for hidden email fields
                    hidden_fields = form.find_all('input', {'type': 'hidden'})
                    for field in hidden_fields:
                        value = field.get('value', '')
                        if '@' in value:
                            found_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", value)
                            domain_based_emails.extend(found_emails)
            
            # Combine all emails
            all_extracted_emails = (text_emails + mailto_emails + class_emails + 
                                   all_tags_emails + script_emails + meta_emails + 
                                   domain_based_emails)
            
            # Clean and add valid emails to the local set
            for email in all_extracted_emails:
                valid_email = validate_email(email)
                if valid_email:
                    # Skip emails from the ignore domains
                    if not any(ignore_domain in valid_email for ignore_domain in IGNORE_DOMAINS):
                        local_emails.add(valid_email)
        
        except Exception as e:
            pass
        
        return local_emails
    
    # First process the main URL
    main_page_emails = process_url(base_url)
    emails_set.update(main_page_emails)
    
    # Then process contact pages regardless of how many emails we found
    # (to ensure we get the most accurate contact emails)
    for contact_path in CONTACT_PAGES:
        contact_url = urljoin(base_url, contact_path)
        if contact_url != base_url:  # Avoid processing the same URL twice
            try:
                contact_page_emails = process_url(contact_url, is_contact_page=True)
                emails_set.update(contact_page_emails)
            except:
                continue
    
    # Clean and deduplicate emails
    all_emails = clean_and_deduplicate_emails(list(emails_set))
    
    # Prioritize emails with domain matching the website
    domain_emails = [email for email in all_emails if domain and domain in email]
    other_emails = [email for email in all_emails if email not in domain_emails]
    
    # Sort emails with domain emails first
    sorted_emails = sorted(domain_emails) + sorted(other_emails)
    
    return sorted_emails  # Return as a list instead of a comma-separated string

# Function to process Google Sheets
def process_google_sheet(sheet_url):
    try:
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
        df = pd.read_csv(csv_url)
        return df
    except:
        return None

# Streamlit UI
st.title("FunnelStrike's Website Email Extractor")

sheet_url = st.text_input("Paste Google Sheet Link:")
if sheet_url:
    df = process_google_sheet(sheet_url)
    if df is not None:
        column = st.selectbox("Select column containing website links:", df.columns)

        if st.button("Find Emails"):
            all_results = []
            total = len(df[column])
            progress_bar = st.progress(0)
            start_time = time.time()
            extracted_count = 0
            status_text = st.empty()

            for i, website in enumerate(df[column], start=1):
                if website and isinstance(website, str):  # Skip empty URLs
                    # Ensure URL has proper http:// prefix
                    if not website.startswith(('http://', 'https://')):
                        website = 'https://' + website
                        
                    emails = extract_emails(website)
                    extracted_count += len(emails)
                    
                    # Create a row for each email
                    if emails:
                        for email in emails:
                            all_results.append({"Website": website, "Email": email})
                    else:
                        all_results.append({"Website": website, "Email": ""})

                    # Update progress
                    progress_bar.progress(i / total)

                    # Time calculations
                    elapsed_time = time.time() - start_time
                    estimated_total_time = (elapsed_time / i) * total
                    remaining_time = max(0, estimated_total_time - elapsed_time)

                    status_text.text(f"Progress: {i}/{total} | Emails Extracted: {extracted_count} | "
                                    f"Estimated time remaining: {int(remaining_time // 60)} min {int(remaining_time % 60)} sec")
                    time.sleep(0.1)

            # Convert results to DataFrame
            result_df = pd.DataFrame(all_results)

            # Display an easily copyable table with more compact styling
            st.markdown("### Extracted Emails Table")

            # Calculate the height based on the number of rows
            row_height = 30  # Height per row in pixels
            max_rows_visible = 10  # Maximum rows visible without scrolling
            header_height = 40  # Height of the header row in pixels

            # Set the container height to fit up to 10 rows
            if len(result_df) <= max_rows_visible:
                table_height = header_height + (len(result_df) * row_height)  # Exact height for all rows
            else:
                table_height = header_height + (max_rows_visible * row_height)  # Fixed height for 10 rows

            # Create a scrollable container with dynamic height
            st.markdown(f"""
                <div style="height: {table_height}px; overflow-y: auto; border: 1px solid #e6e6e6; border-radius: 5px;">
                    {result_df.to_html(index=False, escape=False, classes="compact-table")}
                </div>
            """, unsafe_allow_html=True)

            # Convert DF for download
            def convert_df(df):
                return df.to_csv(index=False).encode('utf-8')

            csv = convert_df(result_df)
            st.download_button("Download CSV", csv, "emails.csv", "text/csv")
    else:
        st.error("Invalid Google Sheet URL")

# Improved CSS for more compact table
st.markdown("""
    <style>
        .compact-table {
            font-size: 12px;
            width: 100%;
            table-layout: fixed;
            margin: 0;
            border-collapse: collapse;
        }
        .compact-table th, .compact-table td {
            padding: 4px 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            border: 1px solid #ddd;
            color: #000000; /* Black text color */
        }
        .compact-table th:first-child, .compact-table td:first-child {
            width: 40%;
        }
        .compact-table th:last-child, .compact-table td:last-child {
            width: 60%;
        }
        .compact-table tr:nth-child(even) {
            background-color: #f5f5f5;
        }
        .compact-table tr:nth-child(odd) {
            background-color: #f0f0f0; 
        }
        .compact-table th {
            background-color: #f0f0f0;
            position: sticky;
            top: 0;
            z-index: 1;
            color: #000000; 
        }
    </style>
""", unsafe_allow_html=True)
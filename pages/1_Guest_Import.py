import streamlit as st
import pandas as pd
import io
import json
import os
import uuid
import zipfile

# --- ⚙️ App Configuration & State ---
st.set_page_config(layout="wide", page_title="Guest Data Import")
MAPPING_CONFIRMATION_THRESHOLD = 3
FILE_ROW_LIMIT = 50000

# --- DATA & MAPPINGS ---
MAPPINGS_FILE = 'mappings.json'
COUNTRY_CODES = {
    "United Kingdom": "44",
    "United States": "1",
    "France": "33"
}

def load_mappings():
    """Loads mappings, ensuring the truthy values list exists and structure is correct."""
    try:
        with open(MAPPINGS_FILE, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
        if "_truthy_values_for_emailMarketingOk" not in mappings:
            mappings["_truthy_values_for_emailMarketingOk"] = ["yes", "true", "1", "y"]
        for key, value in mappings.items():
            if key != "_truthy_values_for_emailMarketingOk" and not isinstance(value, dict):
                mappings[key] = {item: MAPPING_CONFIRMATION_THRESHOLD for item in value}
        return mappings
    except (FileNotFoundError, json.JSONDecodeError):
        default_mappings = {"_truthy_values_for_emailMarketingOk": ["yes", "true", "1", "y"]}
        with open(MAPPINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_mappings, f, indent=2)
        return default_mappings

def save_mappings(mappings):
    """Saves updated mappings back to the JSON file."""
    with open(MAPPINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2)

# --- SCHEMA and RULES ---
RENAMING_MAP = load_mappings()
STANDARD_COLUMNS = [
    'firstName', 'lastName', 'email', 'phoneNumber', 'mobileNumber', 'guestNotes',
    'emailMarketingOk', 'companyName', 'address1', 'address2', 'city', 'state',
    'country', 'zipCode', 'dateOfBirth', 'dateOfAnniversary', 'originalGuestId'
]
MANUAL_MAPPING_OPTIONS = [col for col in STANDARD_COLUMNS if col != 'guestNotes']

# --- ✨ Helper Functions ---
def split_full_name(df, name_col):
    if name_col not in df.columns: return
    name_series = df[name_col].astype(str)
    split_names = name_series.str.split(r'\s+', n=1, expand=True)
    df['firstName_from_split'] = split_names[0]
    df['lastName_from_split'] = split_names[1]
    single_word_mask = df['lastName_from_split'].isnull() & df['firstName_from_split'].notnull()
    df.loc[single_word_mask, 'lastName_from_split'] = df.loc[single_word_mask, 'firstName_from_split']
    df.loc[single_word_mask, 'firstName_from_split'] = ''

def format_phone_number(phone, hint_country_code=None):
    """Intelligently formats a phone number string with a country code hint."""
    if not isinstance(phone, str) or phone.strip() == '':
        return phone
    
    cleaned_phone = "".join(filter(str.isdigit, phone))
    
    # If the number starts with '+', it's already formatted
    if phone.strip().startswith('+'):
        return phone.strip()
    
    # If a country hint is provided and the number starts with that code
    if hint_country_code and cleaned_phone.startswith(hint_country_code):
        return f"+{cleaned_phone}"
        
    # Heuristic for other common international codes without a hint
    if cleaned_phone.startswith('44') and len(cleaned_phone) > 10: # UK
        return f"+{cleaned_phone}"
    if cleaned_phone.startswith('1') and (len(cleaned_phone) == 11): # US
        return f"+{cleaned_phone}"
    if cleaned_phone.startswith('33') and len(cleaned_phone) > 9: # France
        return f"+{cleaned_phone}"
        
    # Return the original number if no confident transformation can be made
    return phone

# --- 🎨 App UI ---
st.title("👤 Guest Data Import Tool")
st.write("A multi-step tool to clean, format, and validate your guest data.")

uploaded_file = st.file_uploader("Upload your guest CSV file", type="csv")

if uploaded_file and st.session_state.get('uploaded_filename') != uploaded_file.name:
    keys_to_reset = ['preview_df', 'header_confirmed', 'original_df', 'df_after_split', 'df_after_mapping', 'manual_mappings', 'header_row_index', 'encoding']
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.uploaded_filename = uploaded_file.name

# --- Step 1: File Setup ---
if uploaded_file:
    st.subheader("Step 1: File Setup")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.rid = st.text_input("Enter your Restaurant ID (RID)", value=st.session_state.get('rid', ''))
    with col2:
        st.session_state.country_hint = st.selectbox("Select the primary country of the data (for phone formatting)", options=["None"] + list(COUNTRY_CODES.keys()), index=0)

    if 'preview_df' not in st.session_state:
        try:
            uploaded_file.seek(0)
            st.session_state.preview_df = pd.read_csv(uploaded_file, header=None, nrows=8, dtype=str, encoding='utf-8').fillna('')
            st.session_state.encoding = 'utf-8'
        except UnicodeDecodeError:
            st.warning("⚠️ Could not read the file with standard encoding. Trying a more flexible one.")
            uploaded_file.seek(0)
            st.session_state.preview_df = pd.read_csv(uploaded_file, header=None, nrows=8, dtype=str, encoding='latin-1').fillna('')
            st.session_state.encoding = 'latin-1'

    options = []
    for index, row in st.session_state.preview_df.iterrows():
        preview_text = ", ".join(row.iloc[:5].dropna().astype(str))
        options.append(f"Row {index + 1}: {preview_text}")

    selected_option = st.selectbox("Please select the row that contains your headers", options=options, index=st.session_state.get('header_row_index', 0), key='header_selector')
    st.session_state.header_row_index = options.index(selected_option)

    if st.button("Confirm Setup and Continue"):
        header_row_number = st.session_state.header_row_index + 1
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, header=header_row_number - 1, dtype=str, encoding=st.session_state.encoding).fillna('')
        st.session_state.original_df = df
        st.session_state.header_confirmed = True
        st.rerun()

# --- All Subsequent Steps ---
if st.session_state.get('header_confirmed'):
    st.subheader("Data Preview (First 50 Rows)")
    st.dataframe(st.session_state.original_df.head(50))
    
    # --- Step 2: Handle 'Full Name' ---
    st.subheader("Step 2: Handle 'Full Name' (Optional)")
    df_step1 = st.session_state.original_df.copy()
    with st.expander("Expand if your file has a combined 'Full Name' column"):
        name_col_to_split = st.selectbox("Select the column containing the full name", options=["-- None --"] + df_step1.columns.tolist())
        if name_col_to_split != "-- None --":
            split_full_name(df_step1, name_col_to_split)
            if 'firstName' not in df_step1.columns: df_step1['firstName'] = ''
            if 'lastName' not in df_step1.columns: df_step1['lastName'] = ''
            df_step1['firstName'] = df_step1['firstName'].replace('', pd.NA).fillna(df_step1.get('firstName_from_split'))
            df_step1['lastName'] = df_step1['lastName'].replace('', pd.NA).fillna(df_step1.get('lastName_from_split'))
            st.info("✅ 'Full Name' has been split.")
    st.session_state.df_after_split = df_step1

    # --- Step 3: Map Columns ---
    st.subheader("Step 3: Map Your Columns")
    # ... (This logic is unchanged)

    # --- Step 4: Clarify Marketing Consent ---
    st.subheader("Step 4: Clarify Marketing Consent (Optional)")
    # ... (This logic is unchanged)

    # --- Step 5: Combine Notes & Finalize ---
    st.subheader("Step 5: Combine Notes & Finalize")
    # ... (This logic is unchanged, except for the RID input which has been moved)
    
    if st.button("🚀 Process, Clean, and Validate"):
        processed_df = st.session_state.df_after_mapping_display.copy()
        manual_rename_dict_final = {orig: new for orig, new in st.session_state.manual_mappings.items() if new != "-- Leave Unmapped --"}
        processed_df.rename(columns=manual_rename_dict_final, inplace=True)
        
        # --- LEARNING & FORMATTING ---
        # ... (emailMarketingOk, notes, and date logic is unchanged)

        # --- UPDATED Phone Number Formatting ---
        hint_code = COUNTRY_CODES.get(st.session_state.get('country_hint'))
        for phone_col in ['phoneNumber', 'mobileNumber']:
            if phone_col in processed_df.columns:
                processed_df[phone_col] = processed_df[phone_col].apply(format_phone_number, args=(hint_code,))
        
        # --- VALIDATION & DELETION ---
        # ... (This logic is unchanged)

        # --- originalGuestId LOGIC ---
        # ... (This logic is unchanged)
        
        # --- DEDUPLICATION LOGIC ---
        # ... (This logic is unchanged)

        # --- LEARNING COLUMN MAPPINGS ---
        # ... (This logic is unchanged)
            
        # --- FINAL DOWNLOAD ---
        # ... (This logic is unchanged, but now uses st.session_state.rid)
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
        default_mappings = {
            "_truthy_values_for_emailMarketingOk": ["yes", "true", "1", "y"],
            "firstName": {"First Name": 3, "FirstName": 3},
            "lastName": {"Last Name": 3, "LastName": 3, "Surname": 3}
        }
        with open(MAPPINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_mappings, f, indent=2)
        return default_mappings

def save_mappings(mappings):
    """Saves updated mappings back to the JSON file."""
    with open(MAPPINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2)

# --- 📜 New Guest Schema and Rules ---
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
    
    if phone.strip().startswith('+'):
        return phone.strip()
    
    if hint_country_code and cleaned_phone.startswith(hint_country_code):
        return f"+{cleaned_phone}"
        
    if cleaned_phone.startswith('44') and len(cleaned_phone) > 10:
        return f"+{cleaned_phone}"
    if cleaned_phone.startswith('1') and (len(cleaned_phone) == 11):
        return f"+{cleaned_phone}"
    if cleaned_phone.startswith('33') and len(cleaned_phone) > 9:
        return f"+{cleaned_phone}"
        
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
        st.session_state.country_hint = st.selectbox("Select the primary country of the data (for phone formatting)", options=["None"] + list(COUNTRY_CODES.keys()))

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

    st.subheader("Step 3: Map Your Columns")
    df_step2 = st.session_state.df_after_split.copy()
    st.session_state.manual_mappings = st.session_state.get('manual_mappings', {})
    
    reversed_map = {}
    for std, var_dict in RENAMING_MAP.items():
        if std != 'guestNotes' and isinstance(var_dict, dict):
            for var, count in var_dict.items():
                if count >= MAPPING_CONFIRMATION_THRESHOLD:
                    reversed_map[var.lower()] = std
    
    auto_rename_dict = {col: reversed_map[col.lower()] for col in df_step2.columns if col.lower() in reversed_map}
    
    st.info(f"✅ Automatically mapped **{len(auto_rename_dict)}** columns based on confirmed rules.")
    if auto_rename_dict:
        with st.expander("Click here to see the automatically mapped columns"):
            st.table(pd.DataFrame(list(auto_rename_dict.items()), columns=['Your Column', 'Mapped To']))
    
    df_step2.rename(columns=auto_rename_dict, inplace=True)
    
    unmapped_columns = [col for col in df_step2.columns if col not in STANDARD_COLUMNS]
    if unmapped_columns:
        st.warning(f"Map any remaining columns. Unmapped columns will be available for 'Guest Notes' in the next step.")
        cols = st.columns(3)
        for i, col_name in enumerate(unmapped_columns):
            with cols[i % 3]:
                options = ["-- Leave Unmapped --"] + MANUAL_MAPPING_OPTIONS
                st.session_state.manual_mappings[col_name] = st.selectbox(f"Map '**{col_name}**'", options, key=f"map_{col_name}")
    
    st.session_state.df_after_mapping_display = df_step2

    st.subheader("Step 4: Clarify Marketing Consent (Optional)")
    df_step3 = st.session_state.df_after_mapping_display.copy()
    if 'emailMarketingOk' in df_step3.columns:
        truthy_values = [str(v).lower() for v in RENAMING_MAP.get("_truthy_values_for_emailMarketingOk", [])]
        unique_values = df_step3['emailMarketingOk'].str.lower().str.strip().replace('', pd.NA).dropna().unique()
        unknown_values = [v for v in unique_values if v not in truthy_values]
        
        if unknown_values:
            with st.expander("Expand to teach the app new marketing consent values", expanded=True):
                st.warning("Found new values in the marketing column. Please clarify how to handle them.")
                st.session_state.treat_all_non_blank_as_true = st.checkbox("Treat ALL non-blank values as TRUE", key="treat_all_true")
                if not st.session_state.treat_all_non_blank_as_true:
                    st.session_state.new_truthy_values = st.multiselect("OR, select specific values to add to the 'TRUE' list:", options=unknown_values)

    st.subheader("Step 5: Combine Notes & Finalize")
    potential_notes_cols = [col for col in st.session_state.df_after_mapping_display.columns if col not in STANDARD_COLUMNS]
    notes_cols_to_combine = st.multiselect("Select columns to combine into 'guestNotes'", options=potential_notes_cols)

    if st.button("🚀 Process, Clean, and Validate"):
        processed_df = st.session_state.df_after_mapping_display.copy()
        manual_rename_dict_final = {orig: new for orig, new in st.session_state.manual_mappings.items() if new != "-- Leave Unmapped --"}
        processed_df.rename(columns=manual_rename_dict_final, inplace=True)
        
        # --- LEARNING & FORMATTING ---
        if 'new_truthy_values' in st.session_state and st.session_state.new_truthy_values:
            RENAMING_MAP["_truthy_values_for_emailMarketingOk"].extend(st.session_state.new_truthy_values)
            save_mappings(RENAMING_MAP)
            st.toast("🧠 New marketing consent values learned!")
        final_truthy_values = [str(v).lower() for v in RENAMING_MAP.get("_truthy_values_for_emailMarketingOk", [])]
        if 'emailMarketingOk' in processed_df.columns:
            if st.session_state.get('treat_all_non_blank_as_true', False):
                processed_df['emailMarketingOk'] = processed_df['emailMarketingOk'].str.strip().ne('')
            else:
                processed_df['emailMarketingOk'] = processed_df['emailMarketingOk'].str.lower().isin(final_truthy_values)
        if notes_cols_to_combine:
            processed_df['guestNotes'] = processed_df[notes_cols_to_combine].apply(lambda x: ', '.join(x.dropna().astype(str).str.strip().replace('', None).dropna().unique()), axis=1)
        for date_col in ['dateOfBirth', 'dateOfAnniversary']:
            if date_col in processed_df.columns:
                processed_df[date_col] = pd.to_datetime(processed_df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
        for name_col in ['firstName', 'lastName']:
            if name_col in processed_df.columns:
                 processed_df[name_col] = processed_df[name_col].str.title()
        
        hint_code = COUNTRY_CODES.get(st.session_state.get('country_hint'))
        for phone_col in ['phoneNumber', 'mobileNumber']:
            if phone_col in processed_df.columns:
                processed_df[phone_col] = processed_df[phone_col].apply(format_phone_number, args=(hint_code,))
        
        # --- VALIDATION & DELETION ---
        initial_rows = len(processed_df)
        if 'lastName' in processed_df.columns:
            processed_df = processed_df[processed_df['lastName'].str.strip() != '']
        else:
            processed_df = processed_df.iloc[0:0]
        contact_cols = [col for col in ['email', 'phoneNumber', 'mobileNumber'] if col in processed_df.columns]
        if contact_cols:
            all_contacts_blank_mask = processed_df[contact_cols].apply(lambda x: x.str.strip().eq('')).all(axis=1)
            processed_df = processed_df[~all_contacts_blank_mask]
        rows_deleted = initial_rows - len(processed_df)
        st.success(f"✅ Initial validation complete! **{rows_deleted}** invalid rows were deleted.")

        # --- originalGuestId LOGIC ---
        if 'originalGuestId' in processed_df.columns:
            initial_id_rows = len(processed_df)
            processed_df.dropna(subset=['originalGuestId'], inplace=True)
            processed_df = processed_df[processed_df['originalGuestId'].str.strip() != '']
            processed_df.drop_duplicates(subset=['originalGuestId'], keep='first', inplace=True)
            ids_deleted = initial_id_rows - len(processed_df)
            if ids_deleted > 0:
                st.warning(f"🚨 Deleted **{ids_deleted}** rows with blank or duplicate 'originalGuestId' values.")
        else:
            processed_df['originalGuestId'] = [uuid.uuid4().hex for _ in range(len(processed_df))]
            st.info("✅ Created a new 'originalGuestId' column.")

        # --- DEDUPLICATION LOGIC ---
        initial_rows_dedup = len(processed_df)
        for col in ['email', 'phoneNumber', 'mobileNumber']:
            if col in processed_df.columns:
                processed_df[col] = processed_df[col].str.strip().replace('', pd.NA)
        
        dedup_key_series = pd.Series(pd.NA, index=processed_df.index, dtype=str)
        if 'email' in processed_df.columns:
            dedup_key_series = dedup_key_series.fillna(processed_df['email'])
        if 'phoneNumber' in processed_df.columns:
            dedup_key_series = dedup_key_series.fillna(processed_df['phoneNumber'])
        if 'mobileNumber' in processed_df.columns:
            dedup_key_series = dedup_key_series.fillna(processed_df['mobileNumber'])
        processed_df['dedup_key'] = dedup_key_series
        
        agg_rules = {}
        for col in processed_df.columns:
            if col not in ['firstName', 'lastName', 'dedup_key']:
                if col == 'emailMarketingOk': agg_rules[col] = 'max'
                elif col == 'guestNotes': agg_rules[col] = lambda x: ', '.join(x.dropna().astype(str).unique())
                else: agg_rules[col] = 'first'
        
        if 'firstName' in processed_df.columns and 'lastName' in processed_df.columns and 'dedup_key' in processed_df.columns:
            deduplicated_df = processed_df.groupby(['firstName', 'lastName', 'dedup_key'], as_index=False).agg(agg_rules)
            deduplicated_df.drop(columns=['dedup_key'], inplace=True, errors='ignore')
            rows_merged = initial_rows_dedup - len(deduplicated_df)
            if rows_merged > 0:
                st.info(f"✨ Merged **{rows_merged}** duplicate rows.")
            processed_df = deduplicated_df

        # --- LEARNING COLUMN MAPPINGS ---
        manual_rename_dict_final = {orig: new for orig, new in st.session_state.manual_mappings.items() if new != "-- Leave Unmapped --"}
        new_mappings_learned = False
        for original_name, standard_name in manual_rename_dict_final.items():
            if standard_name not in RENAMING_MAP or not isinstance(RENAMING_MAP[standard_name], dict):
                RENAMING_MAP[standard_name] = {}
            current_count = RENAMING_MAP[standard_name].get(original_name, 0)
            RENAMING_MAP[standard_name][original_name] = current_count + 1
            new_mappings_learned = True
        if new_mappings_learned:
            save_mappings(RENAMING_MAP)
            st.toast("🧠 Mapping suggestions have been updated!")
            
        # --- FINAL DOWNLOAD ---
        final_cols = [col for col in STANDARD_COLUMNS if col in processed_df.columns]
        final_df = processed_df[final_cols]
        st.subheader("Final Processed Data")
        st.dataframe(final_df.head())
        
        rid = st.session_state.get('rid', '')
        if not rid:
            st.error("Please enter a Restaurant ID (RID) to generate the download file.")
        else:
            if len(final_df) > FILE_ROW_LIMIT:
                st.warning(f"Data has {len(final_df)} rows. It will be split into multiple files.")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    num_chunks = (len(final_df) // FILE_ROW_LIMIT) + 1
                    for i in range(num_chunks):
                        chunk = final_df.iloc[i*FILE_ROW_LIMIT:(i+1)*FILE_ROW_LIMIT]
                        chunk_filename = f"{rid}_CLEANED_{i+1}.csv"
                        zf.writestr(chunk_filename, chunk.to_csv(index=False))
                st.download_button(label=f"⬇️ Download All Files ({num_chunks}) as ZIP", data=zip_buffer.getvalue(), file_name=f"{rid}_CLEANED_FILES.zip", mime="application/zip")
            else:
                csv_buffer = io.StringIO()
                final_df.to_csv(csv_buffer, index=False)
                new_filename = f"{rid}_CLEANED.csv"
                st.download_button(label="⬇️ Download Cleaned Guest Data", data=csv_buffer.getvalue(), file_name=new_filename, mime="text/csv")
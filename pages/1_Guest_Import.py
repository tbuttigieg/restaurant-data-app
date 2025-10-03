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

# --- 🧠 File-Based "Memory" for Mappings ---
MAPPINGS_FILE = 'mappings.json'

def load_mappings():
    """Loads mappings, ensuring the truthy values list exists and structure is correct."""
    try:
        with open(MAPPINGS_FILE, 'r') as f:
            mappings = json.load(f)
        if "_truthy_values_for_emailMarketingOk" not in mappings:
            mappings["_truthy_values_for_emailMarketingOk"] = ["yes", "true", "1", "y"]
        for key, value in mappings.items():
            if key != "_truthy_values_for_emailMarketingOk" and not isinstance(value, dict):
                mappings[key] = {item: MAPPING_CONFIRMATION_THRESHOLD for item in value}
        return mappings
    except (FileNotFoundError, json.JSONDecodeError):
        return {"_truthy_values_for_emailMarketingOk": ["yes", "true", "1", "y"]}

def save_mappings(mappings):
    """Saves updated mappings back to the JSON file."""
    with open(MAPPINGS_FILE, 'w') as f:
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

# --- 🎨 App UI ---
st.title("👤 Guest Data Import Tool")
st.write("A multi-step tool to clean, format, and validate your guest data.")

uploaded_file = st.file_uploader("Upload your guest CSV file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file, dtype=str).fillna('')
    st.session_state.original_df = df
    st.session_state.original_filename = uploaded_file.name
    st.subheader("Raw Data Preview (First 50 Rows)")
    st.dataframe(df.head(50))

if 'original_df' in st.session_state:
    st.subheader("Step 1: Handle 'Full Name' (Optional)")
    df = st.session_state.original_df.copy()
    with st.expander("Expand if your file has a combined 'Full Name' column"):
        name_col_to_split = st.selectbox("Select the column containing the full name", options=["-- None --"] + df.columns.tolist())
        if name_col_to_split != "-- None --":
            split_full_name(df, name_col_to_split)
            if 'firstName' not in df.columns: df['firstName'] = ''
            if 'lastName' not in df.columns: df['lastName'] = ''
            df['firstName'] = df['firstName'].replace('', pd.NA).fillna(df['firstName_from_split'])
            df['lastName'] = df['lastName'].replace('', pd.NA).fillna(df['lastName_from_split'])
            st.info("✅ 'Full Name' has been split.")
    st.session_state.df_after_split = df

if 'df_after_split' in st.session_state:
    st.subheader("Step 2: Map Your Columns")
    df = st.session_state.df_after_split.copy()
    if 'manual_mappings' not in st.session_state: st.session_state.manual_mappings = {}
    
    reversed_map = {}
    for std, var_dict in RENAMING_MAP.items():
        if std != 'guestNotes' and isinstance(var_dict, dict):
            for var, count in var_dict.items():
                if count >= MAPPING_CONFIRMATION_THRESHOLD:
                    reversed_map[var.lower()] = std
    
    auto_rename_dict = {col: reversed_map[col.lower()] for col in df.columns if col.lower() in reversed_map}
    
    st.info(f"✅ Automatically mapped **{len(auto_rename_dict)}** columns based on confirmed rules.")
    if auto_rename_dict:
        with st.expander("Click here to see the automatically mapped columns"):
            mapping_df = pd.DataFrame(list(auto_rename_dict.items()), columns=['Your Column', 'Mapped To'])
            st.table(mapping_df)

    df.rename(columns=auto_rename_dict, inplace=True)
    
    unmapped_columns = [col for col in df.columns if col not in STANDARD_COLUMNS]
    if unmapped_columns:
        st.warning(f"Map any remaining columns. Unmapped columns will be available for 'Guest Notes' in the next step.")
        cols = st.columns(3)
        for i, col_name in enumerate(unmapped_columns):
            with cols[i % 3]:
                options = ["-- Leave Unmapped --"] + MANUAL_MAPPING_OPTIONS
                st.session_state.manual_mappings[col_name] = st.selectbox(f"Map '**{col_name}**'", options, key=f"map_{col_name}")
    
    manual_rename_dict = {orig: new for orig, new in st.session_state.manual_mappings.items() if new != "-- Leave Unmapped --"}
    df.rename(columns=manual_rename_dict, inplace=True)
    st.session_state.df_after_mapping = df

if 'df_after_mapping' in st.session_state:
    st.subheader("Step 3: Clarify Marketing Consent (Optional)")
    df = st.session_state.df_after_mapping.copy()
    
    if 'emailMarketingOk' in df.columns:
        truthy_values = [str(v).lower() for v in RENAMING_MAP.get("_truthy_values_for_emailMarketingOk", [])]
        unique_values = df['emailMarketingOk'].str.lower().str.strip().replace('', pd.NA).dropna().unique()
        unknown_values = [v for v in unique_values if v not in truthy_values]
        
        if unknown_values:
            with st.expander("Expand to teach the app new marketing consent values", expanded=True):
                st.warning("Found new values in the marketing column. Please clarify how to handle them.")
                st.session_state.treat_all_non_blank_as_true = st.checkbox("Treat ALL non-blank values as TRUE", key="treat_all_true")
                if not st.session_state.treat_all_non_blank_as_true:
                    st.session_state.new_truthy_values = st.multiselect("OR, select specific values to add to the 'TRUE' list:", options=unknown_values)

if 'df_after_mapping' in st.session_state:
    st.subheader("Step 4: Combine Notes & Finalize")
    potential_notes_cols = [col for col, mapping in st.session_state.get('manual_mappings', {}).items() if mapping == "-- Leave Unmapped --"]
    notes_cols_to_combine = st.multiselect("Select columns to combine into 'guestNotes'", options=potential_notes_cols)
    
    # --- NEW: Get Restaurant ID ---
    rid = st.text_input("Enter your Restaurant ID (RID) for the output filename")

    if st.button("🚀 Process, Clean, and Validate"):
        processed_df = st.session_state.df_after_mapping.copy()
        
        # --- LEARNING & FORMATTING ---
        # ... (This logic is unchanged)
        
        # --- VALIDATION & DELETION ---
        # ... (This logic is unchanged)

        # --- originalGuestId LOGIC ---
        # ... (This logic is unchanged)

        # --- DEDUPLICATION LOGIC ---
        # ... (This logic is unchanged)

        # --- LEARNING COLUMN MAPPINGS ---
        # ... (This logic is unchanged)
            
        # --- NEW: FINAL DOWNLOAD LOGIC ---
        final_cols = [col for col in STANDARD_COLUMNS if col in processed_df.columns]
        final_df = processed_df[final_cols]
        
        st.subheader("Final Processed Data")
        st.dataframe(final_df.head())
        
        if not rid:
            st.error("Please enter a Restaurant ID (RID) to generate the download file.")
        else:
            if len(final_df) > FILE_ROW_LIMIT:
                # --- Scenario A: Create a ZIP file for multiple CSVs ---
                st.warning(f"Data has {len(final_df)} rows. It will be split into multiple files.")
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Split dataframe into chunks
                    num_chunks = (len(final_df) // FILE_ROW_LIMIT) + 1
                    for i in range(num_chunks):
                        chunk = final_df.iloc[i*FILE_ROW_LIMIT:(i+1)*FILE_ROW_LIMIT]
                        chunk_filename = f"{rid}_CLEANED_{i+1}.csv"
                        zf.writestr(chunk_filename, chunk.to_csv(index=False))
                
                st.download_button(
                    label=f"⬇️ Download All Files ({num_chunks}) as ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"{rid}_CLEANED_FILES.zip",
                    mime="application/zip"
                )
            else:
                # --- Scenario B: Create a single CSV ---
                csv_buffer = io.StringIO()
                final_df.to_csv(csv_buffer, index=False)
                
                new_filename = f"{rid}_CLEANED.csv"
                st.download_button(
                    label="⬇️ Download Cleaned Guest Data",
                    data=csv_buffer.getvalue(),
                    file_name=new_filename,
                    mime="text/csv"
                )
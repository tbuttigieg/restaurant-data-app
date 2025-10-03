import streamlit as st
import pandas as pd
import io
import json

# --- 🧠 File-Based "Memory" for Mappings ---
MAPPINGS_FILE = 'mappings.json'

def load_mappings():
    """Loads the header mappings from the JSON file."""
    try:
        with open(MAPPINGS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # If the file doesn't exist, create it with a default structure
        default_mappings = {
            "firstName": ["First Name", "FirstName", "first_name"],
            "lastName": ["Last Name", "LastName", "Surname", "last_name"],
            "email": ["Email Address", "email_address", "E-Mail"],
            "phone": ["Phone Number", "phone_number"],
            "guest_notes": ["Guest Notes", "Notes"],
            "dietary_notes": ["Dietary Needs", "Dietary Restrictions"]
        }
        with open(MAPPINGS_FILE, 'w') as f:
            json.dump(default_mappings, f, indent=2)
        return default_mappings

# --- ✨ Helper Functions ---
def standardize_headers(df, mappings):
    """Standardizes the headers of a dataframe based on the mapping rules."""
    # Create a reverse map for quick lookup, converting all variations to lowercase
    reversed_map = {var.lower(): std for std, var_list in mappings.items() for var in var_list}
    
    rename_dict = {}
    for col in df.columns:
        if col.lower() in reversed_map:
            rename_dict[col] = reversed_map[col.lower()]
            
    return df.rename(columns=rename_dict)

# --- 🎨 App UI ---
st.title("Merge Multiple CSVs by ID 🔗")
st.write(
    """
    This tool joins multiple CSV files using a common ID. It will automatically standardize headers 
    and combine notes from all files.
    """
)

# --- 1. File Uploader ---
uploaded_files = st.file_uploader(
    "Choose your CSV files (at least two)",
    accept_multiple_files=True,
    type="csv"
)

# --- 2. Find Common Columns (after potential standardization) ---
common_columns = []
if len(uploaded_files) > 1:
    try:
        mappings = load_mappings()
        all_column_sets = []
        for f in uploaded_files:
            f.seek(0)
            # Read only the first row to get headers, which is faster
            temp_df = pd.read_csv(f, nrows=0)
            standardized_df = standardize_headers(temp_df, mappings)
            all_column_sets.append(set(standardized_df.columns))
        
        if all_column_sets:
            common_columns_set = set.intersection(*all_column_sets)
            common_columns = sorted(list(common_columns_set))

    except Exception as e:
        st.error(f"Could not read columns from files. Error: {e}")

id_column = st.selectbox(
    "Select the common ID column to merge on",
    options=common_columns,
    index=None,
    placeholder="Choose a column...",
    disabled=(not common_columns)
)

# --- 3. Processing Logic ---
if st.button("Merge Files", disabled=(not id_column)):
    try:
        mappings = load_mappings()
        
        # Step 1: Standardize all dataframes and store them
        standardized_dfs = []
        for file in uploaded_files:
            file.seek(0)
            df = pd.read_csv(file)
            standardized_df = standardize_headers(df, mappings)
            standardized_dfs.append(standardized_df)

        # Step 2: Get a master list of all unique IDs and all unique columns
        all_ids = pd.concat([df[id_column] for df in standardized_dfs if id_column in df.columns]).dropna().unique()
        all_cols = set(col for df in standardized_dfs for col in df.columns)
        
        # Step 3: Build the final dataframe piece by piece
        final_df = pd.DataFrame({id_column: all_ids})

        for col_name in sorted(list(all_cols)):
            if col_name == id_column:
                continue

            # Start with an empty series for this column
            final_series = pd.Series(index=final_df[id_column], dtype='object', name=col_name)

            # Go through each dataframe and fill in the data for the current column
            for df in standardized_dfs:
                if col_name in df.columns:
                    # Create a temporary series with the ID as the index
                    temp_series = df.set_index(id_column)[col_name].dropna()
                    
                    # For notes, append new info. For others, fill in blanks.
                    if any(keyword in col_name.lower() for keyword in ['notes', 'tags', 'dietary']):
                        final_series = final_series.combine(temp_series, 
                            lambda s1, s2: f"{s1} | {s2}" if pd.notna(s1) and pd.notna(s2) else s1 if pd.notna(s1) else s2
                        )
                    else:
                        final_series.fillna(temp_series, inplace=True)
            
            final_df[col_name] = final_series.values

        st.success("Files merged and cleaned successfully!")

        st.subheader("Merged Data Preview")
        st.dataframe(final_df.head())
        st.info(f"Total rows in final file: **{len(final_df)}**. Total columns: **{len(final_df.columns)}**.")

        csv_buffer = io.StringIO()
        final_df.to_csv(csv_buffer, index=False)
        
        st.download_button(
            label="⬇️ Download Cleaned CSV",
            data=csv_buffer.getvalue(),
            file_name="merged_data_cleaned.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"An error occurred during the merge: {e}. Please check your files.")
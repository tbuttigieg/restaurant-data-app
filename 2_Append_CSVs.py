import streamlit as st
import pandas as pd
import io

# --- 🎨 App UI ---
st.title("Append Multiple CSVs ➕")
st.write(
    """
    This tool stacks multiple CSV files into one. 
    **Important:** All files must have the exact same column headers to work correctly.
    """
)

# --- 1. File Uploader ---
uploaded_files = st.file_uploader(
    "Choose your CSV files",
    accept_multiple_files=True,
    type="csv"
)

# --- 2. Processing Logic ---
if st.button("Append Files", disabled=(not uploaded_files)):
    if uploaded_files:
        try:
            # Create a list to hold all the individual DataFrames
            df_list = []
            
            # Read each uploaded file into a DataFrame and add it to the list
            for file in uploaded_files:
                # IMPORTANT: Reset the file pointer to the beginning for each read
                file.seek(0)
                df_list.append(pd.read_csv(file))

            # Concatenate all DataFrames in the list into a single one
            combined_df = pd.concat(df_list, ignore_index=True)
            
            st.success("Files appended successfully!")
            
            # Show a preview of the combined data
            st.subheader("Combined Data Preview")
            st.dataframe(combined_df.head())
            st.info(f"Total rows in combined file: **{len(combined_df)}**")

            # --- 3. Download Button ---
            csv_buffer = io.StringIO()
            combined_df.to_csv(csv_buffer, index=False)
            
            st.download_button(
                label="⬇️ Download Combined CSV",
                data=csv_buffer.getvalue(),
                file_name="appended_data.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"An error occurred: {e}. Please ensure all files have identical headers.")
    else:
        st.warning("Please upload at least two CSV files.")
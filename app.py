import streamlit as st

# Set the page configuration for the whole app
st.set_page_config(
    page_title="Data Import Toolkit",
    page_icon="🍽️",
    layout="centered"
)

# Display the main title and introduction
st.title("Welcome to the Data Import Toolkit! 🍽️")

st.sidebar.success("Select a tool above to get started.")

st.write(
    """
    This is a collection of tools designed to help you format restaurant data files.

    ### What can you do?
    - **Guest Import**: Format single CSV files ready for Import.
    - **Append CSVs**: Combine multiple csv with exact same headers into one
     - **Merge CSVs**: Combine multiple csv using a look up field (Tock Guest Imports)

    **To begin, select a tool from the navigation sidebar on the left.**
    """
)
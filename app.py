import streamlit as st

# Set the page configuration for the whole app
st.set_page_config(
    page_title="Restaurant Data Toolkit",
    page_icon="🍽️",
    layout="centered"
)

# Display the main title and introduction
st.title("Welcome to the Restaurant Data Toolkit! 🍽️")

st.sidebar.success("Select a tool above to get started.")

st.write(
    """
    This is a collection of tools designed to help you clean, merge, 
    and format your restaurant's data files.

    ### What can you do?
    - **Clean a Single File**: The tool you've already been using.
    - (More tools will be added here in Phase 2)

    **To begin, select a tool from the navigation sidebar on the left.**
    """
)
import streamlit as st
import pandas as pd
import os
import sqlite3
from serpapi import GoogleSearch
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

# Set API keys securely
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "14e0132c351cfff84f37d33c0586681205bfacea732be5ae4df224e6cfefd7ca")
GROQ_API_URL = "https://api.groq.com/openai/v1/generate"  # Replace with the actual Groq API endpoint

# Streamlit page setup
st.set_page_config(page_title="Automated Information Retrieval", layout="wide")
st.title("Automated Information Retrieval")
st.write("Upload a CSV file or connect to Google Sheets to retrieve and process data.")

# Sidebar setup
st.sidebar.header("Step 1: Choose Action")
action = st.sidebar.radio("What would you like to do?", ("Scrape Data", "View Database", "Train & Query Groq API"))

# SQLite Database Setup
conn = sqlite3.connect("scraped_results.db")
c = conn.cursor()

# Create a table to store the search results if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT,
    url TEXT,
    title TEXT,
    snippet TEXT
)''')
conn.commit()

    
# Function to perform SerpAPI search
def search_web(query):
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY
    }
    search = GoogleSearch(params)
    return search.get_dict()

# Scrape Data Action
if action == "Scrape Data":
    # Data Upload
    st.sidebar.header("Step 2: Provide Data Source")
    uploaded_file = st.sidebar.file_uploader("Upload a CSV with entities", type="csv")
    query_template = st.sidebar.text_input("Query Template (use {entity} placeholder)", "Find contact details for {entity}.")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.write("### Uploaded Data")
        st.dataframe(df)
        entity_column = st.selectbox("Select Entity Column", df.columns)

        if st.button("Start Scraping"):
            result_data = []
            for entity in df[entity_column]:
                query = query_template.replace("{entity}", entity)
                st.write(f"Searching for: {query}")
                
                try:
                    results = search_web(query)
                    if 'organic_results' in results:
                        for result in results['organic_results']:
                            result_data.append({
                                "Entity": entity,
                                "URL": result.get('link', 'N/A'),
                                "Title": result.get('title', 'N/A'),
                                "Snippet": result.get('snippet', 'N/A')
                            })
                    else:
                        st.warning(f"No results found for query: {query}")
                except Exception as e:
                    st.error(f"Error during web search for {entity}: {e}")
            
            # Display and store results
            if result_data:
                st.write("### Scraped Results")
                result_df = pd.DataFrame(result_data)
                st.dataframe(result_df)

                # Save results in SQLite database
                for data in result_data:
                    c.execute('''INSERT INTO search_results (entity, url, title, snippet) 
                                 VALUES (?, ?, ?, ?)''', 
                              (data["Entity"], data["URL"], data["Title"], data["Snippet"]))
                conn.commit()
                st.success("Results saved to database.")

                # Option to download results
                csv = result_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download Results as CSV", csv, "search_results.csv", "text/csv")

# View Database Action
elif action == "View Database":
    st.write("### Stored Results in Database")
    c.execute("SELECT * FROM search_results")
    rows = c.fetchall()
    if rows:
        stored_df = pd.DataFrame(rows, columns=["ID", "Entity", "URL", "Title", "Snippet"])
        st.dataframe(stored_df)
    else:
        st.warning("No data found in the database.")

# Train & Query Groq API Action
elif action == "Train & Query Groq API":
    # Train Groq API
    st.sidebar.header("Step 2: Train Groq API")
    train = st.sidebar.button("Train API with Stored Data")
    
    if train:
        c.execute("SELECT * FROM search_results")
        rows = c.fetchall()
        if rows:
            training_data = [{"entity": row[1], "url": row[2], "title": row[3], "snippet": row[4]} for row in rows]
            st.write("### Training Data")
            st.json(training_data)
            
            try:
                response = requests.post(GROQ_API_URL, json={"data": training_data})
                if response.status_code == 200:
                    st.success("Training completed successfully.")
                else:
                    st.error(f"Groq API Error: {response.status_code}, {response.text}")
            except Exception as e:
                st.error(f"Failed to connect to Groq API: {e}")
        else:
            st.warning("No data available for training. Please scrape or upload data first.")

    # Query Groq API
    st.sidebar.header("Step 3: Query Groq API")
    query_input = st.sidebar.text_input("Enter your query (use {entity} placeholder)", "Retrieve URLs for {entity}.")
    
    if st.sidebar.button("Submit Query"):
        if "{entity}" not in query_input:
            st.error("Query must include the {entity} placeholder.")
        else:
            c.execute("SELECT DISTINCT entity FROM search_results")
            entities = [row[0] for row in c.fetchall()]
            results = []

            for entity in entities:
                query = query_input.replace("{entity}", entity)
                st.write(f"Querying Groq API for: {query}")
                try:
                    response = requests.post(GROQ_API_URL, json={"query": query})
                    if response.status_code == 200:
                        api_results = response.json()
                        results.extend(api_results)
                    else:
                        st.error(f"Groq API Query Error: {response.status_code}, {response.text}")
                except Exception as e:
                    st.error(f"Failed to connect to Groq API: {e}")

            if results:
                st.write("### Query Results")
                st.json(results)

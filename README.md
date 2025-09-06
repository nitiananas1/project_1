Misinformation Detector Web App
This is a web-based tool built with React to analyze text and articles for potential misinformation, scams, and biases using the Google Gemini and Google Search APIs.

Features
AI-Powered Analysis: Uses the Gemini 1.5 Flash model to provide a verdict, truthfulness score, and summary.

Scam Categorization: Automatically identifies the type of scam (e.g., Financial Fraud, Health Misinformation).

Actionable Advice: Provides official links to report scams (focused on Indian authorities) and safety tips.

Related News: Searches Google for legitimate news articles related to the suspicious claim.

Entity Recognition: Identifies people, organizations, and locations mentioned in the text.

No Backend Needed: Runs entirely in the browser.

How to Set Up and Run
This project runs directly in your web browser. No complex setup is required.

1. Get Your API Keys
This is the most important step. The application needs API keys to communicate with Google's services.

A. Google AI (Gemini) API Key (Required)

Go to Google AI Studio: https://aistudio.google.com/

Sign in with your Google account.

Click "Get API key" on the left menu.

Click "Create API key in new project".

Copy the generated key. You will paste this into the web app.

B. Google Search API Key & Search Engine ID (Optional)
These are needed for the "Related News" feature.

Get the API Key:

Go to the Google Cloud Console.

Enable the "Custom Search API".

Go to APIs & Services > Credentials, click + CREATE CREDENTIALS, and select API key.

Copy this key.

Get the Search Engine ID:

Go to the Programmable Search Engine page.

Create a new search engine.

Important: Select the option to "Search the entire web".

After creating, copy the "Search engine ID" from the setup page.

2. Run the Application
Download the index.html and app.jsx files into the same folder on your computer.

Open the index.html file in your web browser (like Chrome or Firefox).

The web application will load.

Paste your API keys into the configuration fields at the top of the page.

Start analyzing text!

How to Share
You can upload the entire folder (with index.html, app.jsx, and this README.md) to a GitHub repository. Your friends can then download the folder, follow the instructions in this README to get their own keys, and open the index.html file to use the app.
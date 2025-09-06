# ==============================================================================
# BACKEND SERVER: server.py
# ==============================================================================

# --- PART 1: IMPORTS & SETUP ---
import os
import json
import logging
from typing import Dict, Any, List, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

import google.generativeai as genai
import docx
import pdfplumber
import pytesseract
import spacy
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image
from googleapiclient.discovery import build

# Load configuration from the .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- PART 2: THE ANALYSIS CLASS (Unchanged) ---
# This is the same class we built before
class MisinformationAnalyzer:
    def __init__(self, config: Dict[str, str]):
        if not config.get("GEMINI_API_KEY"):
            raise ValueError("Google Gemini API key not found in .env file.")
        genai.configure(api_key=config["GEMINI_API_KEY"])

        pytesseract.pytesseract.tesseract_cmd = config.get("TESSERACT_CMD_PATH")
        self.config = config
        self.gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        self.spacy_nlp = spacy.load("en_core_web_sm")

        try:
            if config.get("SEARCH_API_KEY") and config.get("SEARCH_ENGINE_ID"):
                self.google_search_service = build("customsearch", "v1", developerKey=config["SEARCH_API_KEY"])
            else:
                self.google_search_service = None
        except Exception:
            self.google_search_service = None

    def _get_text_from_input(self, text_input: str) -> Optional[str]:
        # A simplified version for a web server; it assumes text is sent directly
        # You can expand this to handle URLs passed from the frontend if needed
        return text_input

    def _analyze_text_with_gemini(self, text: str) -> Optional[Dict[str, Any]]:
        prompt = f"""
        Act as a professional fact-checker. Analyze the following text.
        Provide your complete analysis as a single JSON object with the following keys:
        - "verdict": (string, either "REAL" or "FAKE")
        - "sentiment": (string, e.g., "Neutral", "Biased")
        - "truthfulness_score": (integer, from 0 to 100)
        - "main_claim": (string, a one-sentence summary of the main claim)
        - "analysis_summary": (string, a 2-3 sentence explanation for your verdict)
        - "scam_category": (string, if FAKE, choose ONE from: "Financial Fraud", "Health Misinformation", "Impersonation", "Job Scam", "General Fake News". If REAL, use "N/A".)
        - "named_entities": (an object with keys like "PERSON", "ORG" and values as lists of unique strings)
        Do not include any formatting outside the JSON object itself.
        Text to analyze: --- {text} ---
        """
        try:
            response = self.gemini_model.generate_content(prompt)
            cleaned_response = response.text.strip().lstrip("```json").rstrip("```")
            return json.loads(cleaned_response)
        except Exception as e:
            logging.error(f"Gemini API Error: {e}")
            return None

    def _get_remedies_and_reporting_info(self, scam_category: str) -> Dict[str, Any]:
        link_map = {
            "Financial Fraud": {"link": "https://sachet.rbi.org.in/", "description": "Report to the RBI's Sachet portal."},
            "Health Misinformation": {"link": "https://factcheck.pib.gov.in/", "description": "Report to the Press Information Bureau (PIB) Fact Check unit."},
            "General Fake News": {"link": "https://factcheck.pib.gov.in/", "description": "Report to the Press Information Bureau (PIB) Fact Check unit."},
            "Job Scam": {"link": "https://cybercrime.gov.in/", "description": "Report to the National Cyber Crime Portal."},
            "Impersonation": {"link": "https://cybercrime.gov.in/", "description": "Report to the National Cyber Crime Portal."}
        }
        info = link_map.get(scam_category, link_map["General Fake News"])
        return {
            "title": f"🚨 Actions & Remedies for: {scam_category}",
            "reporting_link": info["link"],
            "reporting_description": info["description"],
            "remedies": ["Verify info with trusted sources.", "Be skeptical of sensational offers.", "Never share personal financial data."]
        }

    def _get_related_news(self, query: str) -> Optional[List[Dict[str, str]]]:
        if not self.google_search_service: return None
        try:
            result = self.google_search_service.cse().list(q=query, cx=self.config.get("SEARCH_ENGINE_ID"), num=3).execute()
            return [{"title": item['title'], "link": item['link']} for item in result.get('items', [])]
        except Exception as e:
            logging.error(f"Google Search API Error: {e}")
            return None

    def run_full_analysis(self, text_to_analyze: str) -> Optional[Dict[str, Any]]:
        extracted_text = self._get_text_from_input(text_to_analyze)
        if not extracted_text: return {"error": "Input text is empty."}
        
        gemini_analysis = self._analyze_text_with_gemini(extracted_text)
        if not gemini_analysis: return {"error": "Failed to get analysis from Gemini API."}
        
        final_report = {"gemini_report": gemini_analysis}
        
        if gemini_analysis.get("verdict") == "FAKE":
            scam_category = gemini_analysis.get("scam_category", "General Fake News")
            final_report["remedies_report"] = self._get_remedies_and_reporting_info(scam_category)
            main_claim = gemini_analysis.get("main_claim")
            if main_claim:
                final_report["related_news"] = self._get_related_news(main_claim)
        
        return final_report


# --- PART 3: FLASK SERVER SETUP ---
app = Flask(__name__)
CORS(app)  # This enables the frontend to communicate with the backend

# Load the analyzer once when the server starts
app_config = {
    "GEMINI_API_KEY": os.getenv("GOOGLE_API_KEY"),
    "TESSERACT_CMD_PATH": os.getenv("TESSERACT_CMD_PATH"),
    "SEARCH_API_KEY": os.getenv("GOOGLE_SEARCH_API_KEY"),
    "SEARCH_ENGINE_ID": os.getenv("GOOGLE_SEARCH_ENGINE_ID")
}
analyzer = MisinformationAnalyzer(config=app_config)

@app.route('/analyze', methods=['POST'])
def analyze_endpoint():
    """API endpoint to handle analysis requests from the frontend."""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    text_to_analyze = data['text']
    try:
        result = analyzer.run_full_analysis(text_to_analyze)
        if result and "error" in result:
             return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        logging.error(f"A critical error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    # Runs the server on http://127.0.0.1:5000
    app.run(port=5000, debug=True)

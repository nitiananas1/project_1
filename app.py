# ==============================================================================
# FINAL SCRIPT: SATYA-SAARTHII - MISINFORMATION ANALYZER
# Date: 31 August 2025
# ==============================================================================

# --- PART 1: IMPORTS & SETUP ---
import os
import json
import logging
import traceback
from typing import Dict, Any, List, Optional

import streamlit as st
import google.generativeai as genai
import docx
import pdfplumber
import pytesseract
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pdf2image import convert_from_path
from PIL import Image
from googleapiclient.discovery import build

# Configure professional logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load configuration from the .env file
load_dotenv()


# --- PART 2: THE BACKEND ANALYSIS CLASS ---
class MisinformationAnalyzer:
    """
    A class to encapsulate the entire analysis pipeline, using Gemini for core
    analysis and Google Search for contextual news.
    """
    def __init__(self, config: Dict[str, str]):
        # Configure Gemini API
        if not config.get("GEMINI_API_KEY"):
            raise ValueError("Google Gemini API key not found in .env file.")
        genai.configure(api_key=config["GEMINI_API_KEY"])

        # Configure paths for external tools
        pytesseract.pytesseract.tesseract_cmd = config.get("TESSERACT_CMD_PATH")
        self.poppler_path = config.get("POPPLER_PATH")
        self.config = config

        # Load AI model
        self.gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')

        # Initialize Google Search service, disabling it if keys are missing
        try:
            if config.get("SEARCH_API_KEY") and config.get("SEARCH_ENGINE_ID"):
                self.google_search_service = build("customsearch", "v1", developerKey=config["SEARCH_API_KEY"])
            else:
                self.google_search_service = None
        except Exception as e:
            self.google_search_service = None
            logging.error(f"Could not initialize Google Search service. Feature disabled. Error: {e}")

    def _extract_text_from_docx(self, file_path: str) -> Optional[str]:
        try:
            document = docx.Document(file_path)
            return '\n'.join([para.text for para in document.paragraphs])
        except Exception as e:
            logging.error(f"Error reading docx file {file_path}: {e}")
            return None

    def _extract_text_from_image(self, file_path: str) -> Optional[str]:
        try:
            return pytesseract.image_to_string(Image.open(file_path))
        except Exception as e:
            logging.error(f"Error processing image file {file_path}: {e}")
            return None

    def _extract_text_from_pdf(self, file_path: str) -> Optional[str]:
        full_text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text and len(page_text.strip()) > 50:
                        full_text += page_text + '\n'
                    else: # If direct extraction fails, use OCR
                        try:
                            page_image = convert_from_path(
                                file_path, 300, poppler_path=self.poppler_path,
                                first_page=i + 1, last_page=i + 1
                            )[0]
                            ocr_text = pytesseract.image_to_string(page_image, lang='hin+eng')
                            full_text += ocr_text + '\n'
                        except Exception as ocr_error:
                            logging.error(f"OCR failed for PDF page {i + 1}: {ocr_error}")
                            continue
            return full_text
        except Exception as e:
            logging.error(f"Error reading pdf file {file_path}: {e}")
            return None

    def _fetch_and_extract_from_url(self, url: str) -> Optional[str]:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            paragraphs = soup.find_all('p')
            return '\n'.join([p.get_text() for p in paragraphs])
        except Exception as e:
            logging.error(f"Failed to process URL {url}. Error: {e}")
            return None

    def get_text_from_source(self, source: str) -> Optional[str]:
        """
        Determines the source type (file path, URL, or raw text) and extracts text.
        """
        if source.lower().startswith(('http://', 'https://')):
            return self._fetch_and_extract_from_url(source)
        elif os.path.exists(source):
            _, file_extension = os.path.splitext(source)
            file_extension = file_extension.lower()
            if file_extension == '.docx':
                return self._extract_text_from_docx(source)
            elif file_extension == '.pdf':
                return self._extract_text_from_pdf(source)
            elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
                return self._extract_text_from_image(source)
            else:
                logging.error(f"Unsupported file type '{file_extension}'")
                return None
        else:
            # If it's not a URL or an existing file, assume it's raw text
            return source

    def _analyze_text_with_gemini(self, text: str) -> Optional[Dict[str, Any]]:
        # This updated prompt provides clearer instructions for handling nuanced content
        prompt = f"""
        Act as a professional fact-checker based in India. Analyze the following text.
        A crucial instruction: If the text is accurately reporting a statement someone made (e.g., 'Minister X said Y'), your verdict should be 'REAL' because the *reporting* of the statement is a fact. Your analysis_summary must then clarify this distinction, explaining that while the reporting is real, the content of the statement itself might be misleading.

        Provide your complete analysis as a single JSON object with the following keys:
        - "verdict": (string, either "REAL" or "FAKE")
        - "sentiment": (string, e.g., "Neutral", "Biased", "Provocative")
        - "truthfulness_score": (integer, from 0 to 100)
        - "main_claim": (string, a one-sentence summary of the main claim)
        - "analysis_summary": (string, a 2-3 sentence explanation for your verdict, clarifying any nuance as instructed above)
        - "scam_category": (string, if the verdict is FAKE, choose ONE from: "Financial Fraud", "Health Misinformation", "Impersonation", "Job Scam", "General Fake News". If REAL, use "N/A".)
        - "named_entities": (an object with keys like "PERSON", "ORGANIZATION", "LOCATION" and values as lists of unique strings found in the text)
        
        Do not include any text, notes, or formatting outside the JSON object itself.

        Here is the text to analyze:
        ---
        {text}
        ---
        """
        try:
            response = self.gemini_model.generate_content(prompt)
            # A more robust way to clean potential markdown formatting
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            logging.error("AI returned an invalid JSON format.")
            return None
        except Exception as e:
            logging.error(f"An error occurred with the Gemini API: {e}")
            return None

    def _get_remedies_and_reporting_info(self, scam_category: str) -> Dict[str, Any]:
        link_map = {
            "Financial Fraud": {"link": "https://sachet.rbi.org.in/", "description": "For financial fraud, report to the RBI's Sachet portal and the National Cyber Crime Portal."},
            "Health Misinformation": {"link": "https://factcheck.pib.gov.in/", "description": "Report health-related fake news to the Press Information Bureau (PIB) Fact Check unit."},
            "Job Scam": {"link": "https://cybercrime.gov.in/", "description": "Job scams are a serious crime. Report them immediately to the National Cyber Crime Portal."},
            "Impersonation": {"link": "https://cybercrime.gov.in/", "description": "Report impersonation on the social media platform itself and also to the National Cyber Crime Portal."},
            "General Fake News": {"link": "https://factcheck.pib.gov.in/", "description": "For general fake news, report to the Press Information Bureau (PIB) Fact Check unit."}
        }
        report_info = link_map.get(scam_category, link_map["General Fake News"])
        return {
            "title": f"🚨 Actions & Remedies for: {scam_category}",
            "reporting_link": report_info["link"],
            "reporting_description": report_info["description"],
            "remedies": ["Always verify information with trusted sources before sharing or acting on it.", "Be skeptical of offers that seem too good to be true.", "Never share personal or financial information based on an unsolicited message."]
        }

    def _get_related_news(self, query: str) -> Optional[List[Dict[str, str]]]:
        if not self.google_search_service:
            return None
        try:
            result = self.google_search_service.cse().list(q=query, cx=self.config.get("SEARCH_ENGINE_ID"), num=3).execute()
            return [{"title": item['title'], "link": item['link']} for item in result.get('items', [])]
        except Exception as e:
            logging.error(f"Google Search API request failed: {e}")
            return None

    def run_full_analysis(self, text_to_analyze: str) -> Optional[Dict[str, Any]]:
        gemini_analysis = self._analyze_text_with_gemini(text_to_analyze)
        if not gemini_analysis:
            return {"error": "Failed to get analysis from the AI model."}
        
        final_report = {"gemini_report": gemini_analysis}
        
        # Get related news for ALL verdicts to provide context
        main_claim = gemini_analysis.get("main_claim")
        if main_claim:
            final_report["related_news"] = self._get_related_news(main_claim)
        
        # Only add remedies if the verdict is FAKE
        if gemini_analysis.get("verdict") == "FAKE":
            scam_category = gemini_analysis.get("scam_category", "General Fake News")
            final_report["remedies_report"] = self._get_remedies_and_reporting_info(scam_category)
            
        return final_report


# --- PART 3: THE STREAMLIT FRONTEND ---

# Set the page configuration
st.set_page_config(
    page_title="Satya-Saarthii",
    page_icon="🔎",
    layout="wide"
)

# Use a decorator to cache the analyzer instance, so models are loaded only once
@st.cache_resource
def load_analyzer():
    """Loads the MisinformationAnalyzer and its models."""
    app_config = {
        "GEMINI_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "TESSERACT_CMD_PATH": os.getenv("TESSERACT_CMD_PATH"),
        "POPPLER_PATH": os.getenv("POPPLER_PATH"),
        "SEARCH_API_KEY": os.getenv("GOOGLE_SEARCH_API_KEY"),
        "SEARCH_ENGINE_ID": os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    }
    try:
        analyzer = MisinformationAnalyzer(config=app_config)
        return analyzer
    except Exception as e:
        st.error(f"Failed to initialize the analysis engine: {e}")
        return None

# A helper function to display the report in a structured way
def display_report(report: Dict[str, Any]):
    if not report or "error" in report:
        st.error(f"Analysis Failed: {report.get('error', 'An unknown error occurred.')}")
        return

    gemini_data = report.get("gemini_report", {})
    verdict = gemini_data.get('verdict', 'N/A')
    score = gemini_data.get('truthfulness_score', 0)
    
    st.subheader("Fact-Check Report")
    if verdict == "FAKE":
        st.error(f"**Verdict: {verdict}**")
    else:
        st.success(f"**Verdict: {verdict}**")

    st.progress(score, text=f"Truthfulness Score: {score}%")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Detected Category:** {gemini_data.get('scam_category', 'N/A')}")
    with col2:
        st.warning(f"**Detected Sentiment:** {gemini_data.get('sentiment', 'N/A')}")
        
    st.markdown(f"**Main Claim:** *{gemini_data.get('main_claim', 'N/A')}*")
    st.markdown(f"**Analysis Summary:** {gemini_data.get('analysis_summary', 'N/A')}")

    if "remedies_report" in report:
        remedies_data = report["remedies_report"]
        with st.expander("🚨 Actions & Remedies", expanded=True):
            st.markdown(f"**Recommended Reporting Link:** [{remedies_data['reporting_link']}]({remedies_data['reporting_link']})")
            st.caption(remedies_data['reporting_description'])
            st.markdown("**How to stay safe:**")
            for remedy in remedies_data['remedies']:
                st.markdown(f"- {remedy}")

    if "related_news" in report:
        with st.expander("📰 Related News Articles (from Google Search)", expanded=True):
            news_data = report["related_news"]
            if news_data:
                for article in news_data:
                    st.markdown(f"- **{article['title']}**: [{article['link']}]({article['link']})")
            else:
                st.write("No related news articles were found for the main claim.")
                
    named_entities = gemini_data.get('named_entities', {})
    if named_entities and len(named_entities) > 0:
        with st.expander("✒️ Named Entities Identified by AI"):
            for entity_type, entity_list in named_entities.items():
                st.markdown(f"**{entity_type.title()}:** {', '.join(entity_list)}")

# --- Main App Interface ---
st.title("🔎 Satya-Saarthii: Your Misinformation Detector")
st.markdown("Analyze news articles, documents, or images to detect potential misinformation and scams. (*Satya-Saarthii* means 'Charioteer of Truth'.)")
st.markdown("---")

analyzer = load_analyzer()

if analyzer:
    input_method = st.radio(
        "**Choose your input method:**",
        ("Upload a File", "Enter a URL", "Paste Text"),
        horizontal=True
    )
    
    source_to_process = None

    if input_method == "Upload a File":
        uploaded_file = st.file_uploader(
            "Choose a file (.pdf, .docx, .png, .jpg)",
            type=['pdf', 'docx', 'png', 'jpg', 'jpeg']
        )
        if uploaded_file is not None:
            # Save the uploaded file to a temporary location to get a stable path
            temp_dir = "temp_files"
            if not os.path.exists(temp_dir): os.makedirs(temp_dir)
            
            file_path = os.path.join(temp_dir, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            source_to_process = file_path

    elif input_method == "Enter a URL":
        source_to_process = st.text_input("Enter the URL of the article:")
    
    else: # Paste Text
        source_to_process = st.text_area("Paste the text you want to analyze here:", height=200)

    if st.button("Analyze", type="primary"):
        if source_to_process and source_to_process.strip():
            with st.spinner('Analyzing... This may take a moment.'):
                try:
                    # The get_text_from_source method handles all source types
                    report_text = analyzer.get_text_from_source(source_to_process)
                    
                    if not report_text:
                        st.error("Could not extract any text from the provided source.")
                    else:
                        full_report = analyzer.run_full_analysis(report_text)
                        if full_report:
                            display_report(full_report)
                except Exception as e:
                    st.error("A critical error occurred during analysis.")
                    st.code(traceback.format_exc())
        else:
            st.warning("Please provide a file, a URL, or paste some text to analyze.")



# ==============================================================================
# FINAL SCRIPT: MISINFORMATION ANALYZER
# ==============================================================================

# --- PART 1: IMPORTS & SETUP ---
import os
import json
import logging
import traceback
from typing import Dict, Any, List, Optional

import google.generativeai as genai
import docx
import pdfplumber
import pytesseract
import spacy
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


# --- PART 2: THE ANALYSIS PIPELINE CLASS ---
class MisinformationAnalyzer:
    """
    A class to encapsulate the entire analysis pipeline, with features for
    file/URL analysis, scam categorization, and related news searching.
    """
    def __init__(self, config: Dict[str, str]):
        # Configure Gemini API
        if not config.get("GEMINI_API_KEY"):
            raise ValueError("Google Gemini API key not found in .env file.")
        genai.configure(api_key=config["GEMINI_API_KEY"])

        # Configure paths for Tesseract and Poppler
        pytesseract.pytesseract.tesseract_cmd = config.get("TESSERACT_CMD_PATH")
        self.poppler_path = config.get("POPPLER_PATH")
        self.config = config

        # Load AI/ML models once on initialization
        self.gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        self.spacy_nlp = spacy.load("en_core_web_sm")

        # Initialize Google Search service, disabling it if keys are missing
        try:
            if config.get("SEARCH_API_KEY") and config.get("SEARCH_ENGINE_ID"):
                self.google_search_service = build("customsearch", "v1", developerKey=config["SEARCH_API_KEY"])
                logging.info("Google Search service initialized successfully.")
            else:
                self.google_search_service = None
                logging.warning("Google Search credentials not found in .env. Related news feature will be disabled.")
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
                    else:
                        try:
                            page_image = convert_from_path(
                                file_path, 300, poppler_path=self.poppler_path,
                                first_page=i + 1, last_page=i + 1
                            )[0]
                            ocr_text = pytesseract.image_to_string(page_image, lang='hin+eng')
                            full_text += ocr_text + '\n'
                        except Exception as ocr_error:
                            logging.error(f"OCR failed for page {i + 1}: {ocr_error}")
                            continue
            return full_text
        except Exception as e:
            logging.error(f"Error reading pdf file {file_path}: {e}")
            return None

    def _fetch_and_extract_from_url(self, url: str) -> Optional[str]:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            paragraphs = soup.find_all('p')
            return '\n'.join([p.get_text() for p in paragraphs])
        except Exception as e:
            logging.error(f"Failed to process URL {url}. Error: {e}")
            return None

    def _get_text_from_input(self, source: str) -> Optional[str]:
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
            logging.error(f"Input source not found: {source}")
            return None

    def _analyze_text_with_gemini(self, text: str) -> Optional[Dict[str, Any]]:
        prompt = f"""
        Act as a professional fact-checker. Analyze the following text.
        Provide your complete analysis as a single JSON object with the following keys:
        - "verdict": (string, either "REAL" or "FAKE")
        - "sentiment": (string, e.g., "Neutral", "Biased")
        - "truthfulness_score": (integer, from 0 to 100)
        - "main_claim": (string, a one-sentence summary of the main claim)
        - "analysis_summary": (string, a 2-3 sentence explanation for your verdict)
        - "scam_category": (string, if the verdict is FAKE, choose ONE from the following list: "Financial Fraud", "Health Misinformation", "Impersonation", "Job Scam", "General Fake News". If the verdict is REAL, this should be "N/A".)
        - "past_examples": (a list of 1-2 strings with real-world examples that support your analysis)
        
        Do not include any text or formatting outside of the JSON object itself.

        Here is the text to analyze:
        ---
        {text}
        ---
        """
        try:
            response = self.gemini_model.generate_content(prompt)
            cleaned_response = response.text.strip().lstrip("```json").rstrip("```")
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            logging.error("AI returned an invalid JSON format.")
            return None
        except Exception as e:
            logging.error(f"An error occurred with the Gemini API: {e}")
            return None

    def _get_remedies_and_reporting_info(self, scam_category: str) -> Dict[str, Any]:
        link_map = {
            "Financial Fraud": {
                "link": "https://sachet.rbi.org.in/",
                "description": "For financial fraud, report to the RBI's Sachet portal and the National Cyber Crime Portal."
            },
            "Health Misinformation": {
                "link": "https://factcheck.pib.gov.in/",
                "description": "Report health-related fake news to the Press Information Bureau (PIB) Fact Check unit."
            },
            "Job Scam": {
                "link": "https://cybercrime.gov.in/",
                "description": "Job scams are a serious crime. Report them immediately to the National Cyber Crime Portal."
            },
            "Impersonation": {
                "link": "https://cybercrime.gov.in/",
                "description": "Report impersonation on the social media platform itself and also to the National Cyber Crime Portal."
            },
            "General Fake News": {
                "link": "https://factcheck.pib.gov.in/",
                "description": "For general fake news, report to the Press Information Bureau (PIB) Fact Check unit."
            }
        }
        report_info = link_map.get(scam_category, link_map["General Fake News"])
        return {
            "title": f"🚨 Actions & Remedies for: {scam_category}",
            "reporting_link": report_info["link"],
            "reporting_description": report_info["description"],
            "remedies": [
                "Always verify information with trusted sources before sharing or acting on it.",
                "Be skeptical of offers that seem too good to be true.",
                "Never share personal or financial information based on an unsolicited message."
            ]
        }

    def _get_related_news(self, query: str) -> Optional[List[Dict[str, str]]]:
        if not self.google_search_service:
            logging.warning("Skipping related news search because service is not available.")
            return None
        logging.info(f"Searching for related news with query: '{query}'")
        try:
            result = self.google_search_service.cse().list(
                q=query,
                cx=self.config.get("SEARCH_ENGINE_ID"),
                num=3
            ).execute()
            return [{"title": item['title'], "link": item['link']} for item in result.get('items', [])]
        except Exception as e:
            logging.error(f"Google Search API request failed: {e}")
            return None

    def _extract_entities_with_spacy(self, text: str) -> Dict[str, List[str]]:
        doc = self.spacy_nlp(text)
        entities = {}
        for ent in doc.ents:
            entities.setdefault(ent.label_, []).append(ent.text)
        for label in entities:
            entities[label] = list(sorted(set(entities[label])))
        return entities

    def run_full_analysis(self, source: str) -> Optional[Dict[str, Any]]:
        extracted_text = self._get_text_from_input(source)
        if not extracted_text:
            return {"error": "Failed to extract text from the source."}

        gemini_analysis = self._analyze_text_with_gemini(extracted_text)
        if not gemini_analysis:
            return {"error": "Failed to get analysis from Gemini API."}

        spacy_entities = self._extract_entities_with_spacy(extracted_text)
        final_report = {
            "gemini_report": gemini_analysis,
            "named_entities": spacy_entities
        }
        
        if gemini_analysis.get("verdict") == "FAKE":
            scam_category = gemini_analysis.get("scam_category", "General Fake News")
            final_report["remedies_report"] = self._get_remedies_and_reporting_info(scam_category)
            
            main_claim = gemini_analysis.get("main_claim")
            if main_claim:
                final_report["related_news"] = self._get_related_news(main_claim)
        
        return final_report


# --- PART 3: HELPER FUNCTION & MAIN EXECUTION ---
def print_report(report: Dict[str, Any]):
    if not report or "error" in report:
        print(f"\n❌ Analysis Failed: {report.get('error', 'An unknown error occurred.')}")
        return

    print("\n" + "="*50)
    print("✅ AI Fact-Check Report")
    print("="*50)
    
    gemini_data = report.get("gemini_report", {})
    print(f"Verdict: {gemini_data.get('verdict', 'N/A')}")
    print(f"Truthfulness Score: {gemini_data.get('truthfulness_score', 'N/A')}%")
    if gemini_data.get('verdict') == 'FAKE':
        print(f"Detected Category: {gemini_data.get('scam_category', 'N/A')}")
    print(f"Analysis Summary: {gemini_data.get('analysis_summary', 'N/A')}")
    
    if "remedies_report" in report:
        remedies_data = report["remedies_report"]
        print("\n" + "-"*50)
        print(remedies_data['title'])
        print(f"Recommended Reporting Link: {remedies_data['reporting_link']}")
        print(f"Info: {remedies_data['reporting_description']}")
        print("\nHow to stay safe:")
        for remedy in remedies_data['remedies']:
            print(f"- {remedy}")

    if "related_news" in report:
        news_data = report["related_news"]
        print("\n--- 📰 Related News Articles (from Google Search) ---")
        if news_data:
            for article in news_data:
                print(f"- {article['title']}\n  Link: {article['link']}")
        else:
            print("No related news articles were found for the main claim.")

    print("="*50)


if __name__ == "__main__":
    app_config = {
        "GEMINI_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "TESSERACT_CMD_PATH": os.getenv("TESSERACT_CMD_PATH"),
        "POPPLER_PATH": os.getenv("POPPLER_PATH"),
        "SEARCH_API_KEY": os.getenv("GOOGLE_SEARCH_API_KEY"),
        "SEARCH_ENGINE_ID": os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    }
    
    try:
        analyzer = MisinformationAnalyzer(config=app_config)
        source_input = input("Please enter the full file path OR a URL to check: ")
        full_report = analyzer.run_full_analysis(source_input)
        if full_report:
            print_report(full_report)
    except Exception as e:
        print(f"\nA critical error occurred: {e}")
        traceback.print_exc()
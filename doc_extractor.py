# ==============================================================================
# PART 1: IMPORTS & SETUP
# ==============================================================================
import os
import json
import pytesseract
from PIL import Image
import pdfplumber
from pdf2image import convert_from_path
import docx
import google.generativeai as genai
import spacy

# Load the spaCy model once when the script starts
nlp = spacy.load("en_core_web_sm")

# --- YOUR API KEY ---
GOOGLE_API_KEY = "AIzaSyBBJQrT1wdSU7GP5eQH9Jh00cJq0R_fd6I"
genai.configure(api_key=GOOGLE_API_KEY)


# ==============================================================================
# PART 2: DATA EXTRACTION FUNCTIONS (No changes needed)
# ==============================================================================
def extract_text_from_docx(file_path):
    """Extracts text from a .docx file."""
    try:
        document = docx.Document(file_path)
        return '\n'.join([para.text for para in document.paragraphs])
    except Exception as e:
        print(f"Error reading docx file {file_path}: {e}")
        return ""

def extract_text_from_image(file_path):
    """Extracts text from an image file using OCR (Tesseract)."""
    try:
        pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'
        return pytesseract.image_to_string(Image.open(file_path))
    except Exception as e:
        print(f"Error processing image file {file_path}: {e}")
        return ""

def extract_text_from_pdf(file_path):
    """Extracts text from a .pdf file using a hybrid page-by-page approach."""
    full_text = ""
    print(f"Processing PDF: {file_path}")
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                print(f" - Reading page {i + 1}...")
                page_text = page.extract_text()
                if page_text and len(page_text.strip()) > 50:
                    print(f"   ...extracted text directly.")
                    full_text += page_text + '\n'
                else:
                    print(f"   ...direct extraction failed, trying OCR for page {i + 1}.")
                    try:
                        page_image = convert_from_path(
                            file_path,
                            300,
                            poppler_path='/opt/homebrew/bin',
                            first_page=i + 1,
                            last_page=i + 1
                        )[0]
                        ocr_text = pytesseract.image_to_string(page_image, lang='hin+eng')
                        full_text += ocr_text + '\n'
                        print(f"   ...successfully extracted text with OCR.")
                    except Exception as ocr_error:
                        print(f"   ...OCR failed for page {i + 1}: {ocr_error}")
                        continue
        return full_text
    except Exception as e:
        print(f"Error reading pdf file {file_path}: {e}")
        return ""

def extract_text(file_path):
    """Master function to detect file type and extract text."""
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    file_extension = os.path.splitext(file_path)[1].lower()
    print(f"\n--- Processing {file_path} (Type: {file_extension}) ---")
    if file_extension == '.docx':
        return extract_text_from_docx(file_path)
    elif file_extension == '.pdf':
        return extract_text_from_pdf(file_path)
    elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        return extract_text_from_image(file_path)
    else:
        return f"Error: Unsupported file type '{file_extension}'"


# ==============================================================================
# PART 3: AI & NLP ANALYSIS FUNCTIONS (Prompt is updated)
# ==============================================================================
def analyze_text_with_gemini(text_to_analyze):
    """Analyzes text using the Gemini API for a complete fact-check report."""
    if not text_to_analyze or text_to_analyze.strip() == "":
        return "Error: No text to analyze."
        
    # --- UPDATED PROMPT ---
    prompt = f"""
    Act as a professional fact-checker. Analyze the following news article text.
    Provide your complete analysis as a single JSON object with the following keys:
    - "verdict": (string, either "REAL" or "FAKE")
    - "sentiment": (string, e.g., "Neutral", "Biased", "Inflammatory")
    - "truthfulness_score": (integer, from 0 to 100)
    - "main_claim": (string, a one-sentence summary of the main claim)
    - "analysis_summary": (string, a 2-3 sentence explanation for your verdict)
    - "past_examples": (a list of strings, with 1-2 real-world examples or facts from past records that support your analysis)
    
    Do not include any text or formatting outside of the JSON object itself.

    Here is the text to analyze:
    ---
    {text_to_analyze}
    ---
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        analysis_data = json.loads(cleaned_response)
        return analysis_data
    except json.JSONDecodeError:
        return "Error: AI returned an invalid format. Could not parse the analysis."
    except Exception as e:
        return f"An error occurred with the Gemini API: {e}"

def extract_entities_with_spacy(text_to_analyze):
    """Uses spaCy to perform Named Entity Recognition (NER) on the text."""
    if not text_to_analyze or text_to_analyze.strip() == "":
        return {}
    doc = nlp(text_to_analyze)
    entities = {}
    for ent in doc.ents:
        if ent.label_ not in entities:
            entities[ent.label_] = []
        if ent.text not in entities[ent.label_]:
            entities[ent.label_].append(ent.text)
    return entities

def run_full_analysis(file_path):
    """
    Main function that orchestrates the entire analysis pipeline.
    """
    extracted_text = extract_text(file_path)
    if "Error" in str(extracted_text) or not extracted_text:
        return {"error": extracted_text or "Failed to extract text."}

    gemini_analysis = analyze_text_with_gemini(extracted_text)
    if "Error" in str(gemini_analysis):
        return {"error": gemini_analysis}

    spacy_entities = extract_entities_with_spacy(extracted_text)

    final_result = {
        "gemini_report": gemini_analysis,
        "named_entities": spacy_entities
    }
    return final_result


# ==============================================================================
# PART 4: MAIN EXECUTION BLOCK (Updated to print the new examples section)
# ==============================================================================
if __name__ == "__main__":
    file_to_check = input("Please enter the full path to the file you want to check: ")
    
    full_report = run_full_analysis(file_to_check)

    if "error" in full_report:
        print(f"\nAn error occurred: {full_report['error']}")
    else:
        # --- Print the report to the console ---
        print("\n--- AI Fact-Check Report ---")
        gemini_data = full_report.get("gemini_report", {})
        print(f"Verdict: {gemini_data.get('verdict', 'N/A')}")
        print(f"Truthfulness Score: {gemini_data.get('truthfulness_score', 'N/A')}%")
        print(f"Analysis Summary: {gemini_data.get('analysis_summary', 'N/A')}")

        # --- NEW SECTION TO PRINT EXAMPLES ---
        print("\n--- Supporting Examples / Past Records ---")
        past_examples = gemini_data.get('past_examples', [])
        if past_examples:
            for ex in past_examples:
                print(f"- {ex}")
        else:
            print("No specific examples were found.")

        print("\n--- Identified Entities ---")
        entity_data = full_report.get("named_entities", {})
        if entity_data:
            for label, items in entity_data.items():
                print(f"  {label}: {', '.join(items)}")
        else:
            print("  No entities found.")
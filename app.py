import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import os

# Import the master function from your other script
from doc_extractor import run_full_analysis

class FactCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Fake News Detector")
        self.root.geometry("800x700") # Made the window a bit taller

        # --- Create and place the widgets ---

        # 1. A frame to hold the button and a label
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill=tk.X)

        self.info_label = tk.Label(top_frame, text="Select a document (.docx, .pdf, .png, .jpg) to analyze.")
        self.info_label.pack()

        self.select_button = tk.Button(top_frame, text="Select File and Analyze", command=self.start_analysis_thread, font=("Helvetica", 14))
        self.select_button.pack(pady=10)

        # 2. A text area to display the results
        self.result_text = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, state=tk.DISABLED, padx=10, pady=10, font=("Helvetica", 12))
        self.result_text.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

    def start_analysis_thread(self):
        """
        This function is called by the button. It opens the file dialog
        and starts the analysis in a new thread to keep the UI responsive.
        """
        filepath = filedialog.askopenfilename(
            title="Select a file",
            filetypes=(("All supported files", "*.docx *.pdf *.png *.jpg *.jpeg"),
                       ("Word Documents", "*.docx"),
                       ("PDF Documents", "*.pdf"),
                       ("Image Files", "*.png *.jpg *.jpeg"))
        )
        if not filepath:
            return # User cancelled

        # Disable the button and show a "loading" message
        self.select_button.config(state=tk.DISABLED, text="Analyzing...")
        self.display_results(f"Processing file: {os.path.basename(filepath)}\n\nPlease wait, this may take a moment...")

        # Run the actual analysis in a separate thread
        analysis_thread = threading.Thread(target=self.run_analysis, args=(filepath,))
        analysis_thread.start()

    def run_analysis(self, filepath):
        """This function runs in the background thread."""
        try:
            # Call the master function from your other script
            full_report = run_full_analysis(filepath)
            # When done, schedule the display_results function to run on the main UI thread
            self.root.after(0, self.display_final_report, full_report)
        except Exception as e:
            # If there's an unexpected error, show it
            self.root.after(0, messagebox.showerror, "Error", f"An unexpected error occurred: {e}")


    def display_final_report(self, full_report):
        """Formats and displays the final report in the text box."""
        # Re-enable the button
        self.select_button.config(state=tk.NORMAL, text="Select File and Analyze")

        if "error" in full_report:
            self.display_results(f"An error occurred:\n\n{full_report['error']}")
            return

        # --- Format the results into a nice string ---
        gemini_data = full_report.get("gemini_report", {})
        entity_data = full_report.get("named_entities", {})
        
        report_string = "--- AI Fact-Check Report ---\n"
        report_string += f"Verdict: {gemini_data.get('verdict', 'N/A')}\n"
        report_string += f"Truthfulness Score: {gemini_data.get('truthfulness_score', 'N/A')}%\n\n"
        
        report_string += "--- Fact-Check Summary ---\n"
        report_string += f"{gemini_data.get('fact_check_summary', 'No summary available.')}\n\n"

        report_string += "--- Identified Entities ---\n"
        if entity_data:
            for label, items in entity_data.items():
                report_string += f"  {label}: {', '.join(items)}\n"
        else:
            report_string += "  No entities found.\n"
            
        self.display_results(report_string)

    def display_results(self, text_to_display):
        """Helper function to safely update the text box."""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete('1.0', tk.END)
        self.result_text.insert(tk.END, text_to_display)
        self.result_text.config(state=tk.DISABLED)

# --- Run the Application ---
if __name__ == "__main__":
    root = tk.Tk()
    app = FactCheckerApp(root)
    root.mainloop()
const { useState, useEffect } = React;

// --- Helper Icon Components (using SVG) ---
const SunIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-yellow-400"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
);

const AlertTriangleIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-500"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
);

// --- Main App Component ---
const App = () => {
    // --- State Management ---
    const [geminiApiKey, setGeminiApiKey] = useState('');
    const [searchApiKey, setSearchApiKey] = useState('');
    const [searchEngineId, setSearchEngineId] = useState('');
    const [inputText, setInputText] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [analysisResult, setAnalysisResult] = useState(null);
    
    // --- API Call and Analysis Logic ---
    const handleAnalysis = async () => {
        if (!inputText.trim()) {
            setError("Please enter some text or a URL to analyze.");
            return;
        }
        if (!geminiApiKey) {
            setError("Please enter your Google AI Studio (Gemini) API Key.");
            return;
        }

        setIsLoading(true);
        setError(null);
        setAnalysisResult(null);

        const prompt = `
            Act as a professional fact-checker. Analyze the following text.
            Provide your complete analysis as a single JSON object with the following keys:
            - "verdict": (string, either "REAL" or "FAKE")
            - "sentiment": (string, e.g., "Neutral", "Biased")
            - "truthfulness_score": (integer, from 0 to 100)
            - "main_claim": (string, a one-sentence summary of the main claim)
            - "analysis_summary": (string, a 2-3 sentence explanation for your verdict)
            - "scam_category": (string, if the verdict is FAKE, choose ONE from: "Financial Fraud", "Health Misinformation", "Impersonation", "Job Scam", "General Fake News". If REAL, use "N/A".)
            - "named_entities": (an object where keys are entity types like "PERSON", "ORG", "GPE" and values are lists of unique strings found in the text)

            Do not include any text, formatting, or markdown like \`\`\`json outside of the JSON object itself.

            Text to analyze:
            ---
            ${inputText}
            ---
        `;

        try {
            // --- 1. Call Gemini API for the main analysis ---
            const geminiApiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${geminiApiKey}`;
            const geminiResponse = await fetch(geminiApiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
            });

            if (!geminiResponse.ok) {
                const errorData = await geminiResponse.json();
                throw new Error(`Gemini API Error: ${errorData.error.message}`);
            }

            const geminiResult = await geminiResponse.json();
            const rawText = geminiResult.candidates[0].content.parts[0].text;
            const geminiData = JSON.parse(rawText.trim());

            let finalReport = { gemini_report: geminiData, related_news: null };

            // --- 2. If Fake, get remedies and search for related news ---
            if (geminiData.verdict === "FAKE") {
                finalReport.remedies_report = getRemedies(geminiData.scam_category);
                
                if (searchApiKey && searchEngineId && geminiData.main_claim) {
                    const searchApiUrl = `https://www.googleapis.com/customsearch/v1?key=${searchApiKey}&cx=${searchEngineId}&q=${encodeURIComponent(geminiData.main_claim)}&num=3`;
                    const searchResponse = await fetch(searchApiUrl);
                    if (searchResponse.ok) {
                        const searchResult = await searchResponse.json();
                        finalReport.related_news = searchResult.items?.map(item => ({
                            title: item.title,
                            link: item.link,
                        })) || [];
                    }
                }
            }
            setAnalysisResult(finalReport);
        } catch (err) {
            console.error(err);
            setError(`An error occurred: ${err.message}. Check the console for details.`);
        } finally {
            setIsLoading(false);
        }
    };
    
    // --- Helper to get remedies based on category ---
    const getRemedies = (scamCategory) => {
         const linkMap = {
            "Financial Fraud": { link: "https://sachet.rbi.org.in/", description: "For financial fraud, report to the RBI's Sachet portal and the National Cyber Crime Portal." },
            "Health Misinformation": { link: "https://factcheck.pib.gov.in/", description: "Report health-related fake news to the Press Information Bureau (PIB) Fact Check unit." },
            "Job Scam": { link: "https://cybercrime.gov.in/", description: "Job scams are a serious crime. Report them immediately to the National Cyber Crime Portal." },
            "Impersonation": { link: "https://cybercrime.gov.in/", description: "Report impersonation on the social media platform itself and also to the National Cyber Crime Portal." },
            "General Fake News": { link: "https://factcheck.pib.gov.in/", description: "For general fake news, report to the Press Information Bureau (PIB) Fact Check unit." }
        };
        const info = linkMap[scamCategory] || linkMap["General Fake News"];
        return {
            title: `🚨 Actions & Remedies for: ${scamCategory}`,
            reporting_link: info.link,
            reporting_description: info.description,
            remedies: [
                "Always verify information with trusted sources before sharing or acting on it.",
                "Be skeptical of offers that seem too good to be true.",
                "Never share personal or financial information based on an unsolicited message."
            ]
        };
    };

    return (
        <div className="min-h-screen bg-slate-900 text-gray-200 p-4 sm:p-6 lg:p-8">
            <div className="max-w-4xl mx-auto">
                <header className="text-center mb-8">
                    <h1 className="text-4xl sm:text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-cyan-400">
                        Misinformation Detector
                    </h1>
                    <p className="text-slate-400 mt-2">
                        Analyze text or articles for potential misinformation, scams, and biases using AI.
                    </p>
                </header>
                
                <main>
                    {/* --- API Key Inputs --- */}
                    <div className="bg-slate-800 p-4 rounded-lg mb-6 border border-slate-700">
                        <h2 className="text-lg font-semibold mb-3 text-white">API Configuration</h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <input
                                type="password"
                                placeholder="Enter Google AI (Gemini) API Key *"
                                value={geminiApiKey}
                                onChange={(e) => setGeminiApiKey(e.target.value)}
                                className="w-full p-2 bg-slate-700 rounded-md border border-slate-600 focus:ring-2 focus:ring-cyan-500 focus:outline-none"
                            />
                            <input
                                type="password"
                                placeholder="Enter Google Search API Key (Optional)"
                                value={searchApiKey}
                                onChange={(e) => setSearchApiKey(e.target.value)}
                                className="w-full p-2 bg-slate-700 rounded-md border border-slate-600 focus:ring-2 focus:ring-cyan-500 focus:outline-none"
                            />
                            <input
                                type="password"
                                placeholder="Enter Search Engine ID (Optional)"
                                value={searchEngineId}
                                onChange={(e) => setSearchEngineId(e.target.value)}
                                className="w-full p-2 bg-slate-700 rounded-md border border-slate-600 focus:ring-2 focus:ring-cyan-500 focus:outline-none col-span-1 md:col-span-2"
                            />
                        </div>
                    </div>
                    
                    {/* --- Text Input Area --- */}
                    <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            placeholder="Paste the text or URL of the article you want to analyze here..."
                            className="w-full h-48 p-3 bg-slate-700 rounded-md border border-slate-600 focus:ring-2 focus:ring-cyan-500 focus:outline-none resize-none"
                        ></textarea>
                        <button
                            onClick={handleAnalysis}
                            disabled={isLoading}
                            className="mt-4 w-full flex items-center justify-center gap-2 bg-gradient-to-r from-purple-500 to-cyan-500 hover:from-purple-600 hover:to-cyan-600 text-white font-bold py-3 px-4 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
                        >
                            {isLoading ? 'Analyzing...' : 'Analyze Text'}
                        </button>
                    </div>

                    {/* --- Results Display --- */}
                    {isLoading && <div className="text-center mt-6"><p>Loading analysis...</p></div>}
                    {error && <div className="mt-6 bg-red-900/50 text-red-300 p-4 rounded-lg border border-red-800">{error}</div>}
                    {analysisResult && <ResultDisplay result={analysisResult} />}
                </main>
            </div>
        </div>
    );
};

// --- Component to display the final report ---
const ResultDisplay = ({ result }) => {
    const { gemini_report, remedies_report, related_news } = result;
    const { verdict, truthfulness_score, scam_category, sentiment, main_claim, analysis_summary, named_entities } = gemini_report;

    return (
        <div className="mt-8 bg-slate-800 p-6 rounded-lg border border-slate-700 animate-fade-in">
            <h2 className="text-2xl font-bold mb-4">Analysis Report</h2>
            
            <div className={`p-4 rounded-lg mb-4 border ${verdict === 'FAKE' ? 'bg-red-900/30 border-red-700' : 'bg-green-900/30 border-green-700'}`}>
                <span className="font-bold text-xl">{verdict === 'FAKE' ? <AlertTriangleIcon /> : <SunIcon />} Verdict: </span>
                <span className={`font-bold text-xl ${verdict === 'FAKE' ? 'text-red-400' : 'text-green-400'}`}>{verdict}</span>
            </div>

            <div className="w-full bg-slate-700 rounded-full h-2.5 mb-4">
                <div className={`h-2.5 rounded-full ${truthfulness_score < 30 ? 'bg-red-500' : truthfulness_score < 70 ? 'bg-yellow-500' : 'bg-green-500'}`} style={{ width: `${truthfulness_score}%` }}></div>
            </div>
            <p className="text-right text-sm text-slate-400 mb-4">Truthfulness Score: {truthfulness_score}%</p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div className="bg-slate-700 p-3 rounded-lg"><strong>Category:</strong> {scam_category}</div>
                <div className="bg-slate-700 p-3 rounded-lg"><strong>Sentiment:</strong> {sentiment}</div>
            </div>
            
            <div className="bg-slate-700 p-3 rounded-lg mb-4">
                <p><strong>Main Claim:</strong> <em>{main_claim}</em></p>
                <p className="mt-2"><strong>Summary:</strong> {analysis_summary}</p>
            </div>
            
            {remedies_report && (
                <div className="bg-slate-700/50 border border-slate-600 p-4 rounded-lg mb-4">
                    <h3 className="text-lg font-bold mb-2">{remedies_report.title}</h3>
                    <p><strong>Recommended Reporting Link:</strong> <a href={remedies_report.reporting_link} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">{remedies_report.reporting_link}</a></p>
                    <p className="text-sm text-slate-400 mb-2">{remedies_report.reporting_description}</p>
                    <ul className="list-disc list-inside mt-2">
                        {remedies_report.remedies.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                </div>
            )}

            {related_news && (
                 <div className="bg-slate-700/50 border border-slate-600 p-4 rounded-lg mb-4">
                    <h3 className="text-lg font-bold mb-2">Related News Articles</h3>
                    {related_news.length > 0 ? (
                        <ul>
                            {related_news.map((news, i) => (
                                <li key={i} className="mb-2"><a href={news.link} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">{news.title}</a></li>
                            ))}
                        </ul>
                    ) : <p>No related news found.</p>}
                 </div>
            )}

             {named_entities && Object.keys(named_entities).length > 0 && (
                 <div className="bg-slate-700/50 border border-slate-600 p-4 rounded-lg">
                    <h3 className="text-lg font-bold mb-2">Named Entities Found</h3>
                    <div className="flex flex-wrap gap-2">
                        {Object.entries(named_entities).map(([type, values]) => (
                            <div key={type}>
                                <h4 className="font-semibold text-slate-300">{type}</h4>
                                {values.map(val => <span key={val} className="inline-block bg-slate-600 text-slate-200 text-xs font-medium mr-2 px-2.5 py-0.5 rounded-full">{val}</span>)}
                            </div>
                        ))}
                    </div>
                 </div>
            )}
        </div>
    );
};

// --- Render the App to the DOM ---
const domContainer = document.querySelector('#root');
const root = ReactDOM.createRoot(domContainer);
root.render(<App />);
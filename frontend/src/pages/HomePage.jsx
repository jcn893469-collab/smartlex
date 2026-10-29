import { useState } from "react";

import AnalysisPanel from "../components/AnalysisPanel.jsx";
import HealthStatus from "../components/HealthStatus.jsx";
import HistoryPanel from "../components/HistoryPanel.jsx";

const features = [
  {
    title: "Lexical Analysis",
    text: "Break source code into tokens and catch invalid characters and identifiers.",
  },
  {
    title: "Syntax Analysis",
    text: "Validate token sequences with a grammar-based parser.",
  },
  {
    title: "Intelligent Diagnosis",
    text: "Root-cause explanations and correction suggestions for beginners.",
  },
  {
    title: "Adaptive Learning",
    text: "Track error history and get feedback based on your recurring mistakes.",
  },
];

const SAMPLE_SOURCE = `int x = 10;
if (x > 5) {
  x = x + 1;
}`;

export default function HomePage() {
  const [source, setSource] = useState(SAMPLE_SOURCE);
  const [language, setLanguage] = useState("c");

  return (
    <div className="page">
      <header className="hero">
        <h1>SMARTLEX</h1>
        <p className="subtitle">Intelligent Error Diagnosis for Lexical &amp; Syntax Analysis</p>
      </header>

      <main className="content">
        <section className="grid">
          {features.map((f) => (
            <div className="card" key={f.title}>
              <h3>{f.title}</h3>
              <p className="muted">{f.text}</p>
            </div>
          ))}
        </section>

        <AnalysisPanel
          source={source}
          onSourceChange={setSource}
          language={language}
          onLanguageChange={setLanguage}
        />
        <HistoryPanel onLoadSource={setSource} />
        <HealthStatus />
      </main>

      <footer className="footer">
        Compiler Design Project &middot; Vellore Institute of Technology
      </footer>
    </div>
  );
}
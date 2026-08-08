import { useEffect, useState } from "react";
import "./App.css";
import "./review.css";
import { CorrelationQueue } from "./components/review/CorrelationQueue";
import { ExtractionQueue } from "./components/review/ExtractionQueue";

type Tab = "extractions" | "correlations";

export default function ReviewApp() {
  const [tab, setTab] = useState<Tab>("extractions");
  const [reviewerName, setReviewerName] = useState(() => localStorage.getItem("reviewerName") ?? "");

  useEffect(() => {
    localStorage.setItem("reviewerName", reviewerName);
  }, [reviewerName]);

  return (
    <div className="app-shell">
      <header className="app-header review-header">
        <div>
          <h1>Review Queue</h1>
          <p className="app-subtitle">
            Approve or correct AI-extracted datasheets and proposed visbreaking correlations before they go live.
            Nothing here is used by the search tool until you approve it.
          </p>
        </div>
        <a className="btn-secondary" href="/">
          ← Back to search tool
        </a>
      </header>

      <div className="reviewer-bar">
        <label htmlFor="reviewer-name">Reviewing as</label>
        <input
          id="reviewer-name"
          value={reviewerName}
          onChange={(e) => setReviewerName(e.target.value)}
          placeholder="your name"
        />
      </div>

      <nav className="review-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "extractions"}
          className={tab === "extractions" ? "review-tab review-tab-active" : "review-tab"}
          onClick={() => setTab("extractions")}
        >
          PDF Extractions
        </button>
        <button
          role="tab"
          aria-selected={tab === "correlations"}
          className={tab === "correlations" ? "review-tab review-tab-active" : "review-tab"}
          onClick={() => setTab("correlations")}
        >
          Correlation Proposals
        </button>
      </nav>

      <main className="app-main">
        {tab === "extractions" ? (
          <ExtractionQueue reviewerName={reviewerName} />
        ) : (
          <CorrelationQueue reviewerName={reviewerName} />
        )}
      </main>
    </div>
  );
}

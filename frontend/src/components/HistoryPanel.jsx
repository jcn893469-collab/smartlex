import { useEffect, useState } from "react";

import { deleteAnalysisRecord, listAnalysisRecords } from "../services/api.js";

export default function HistoryPanel({ onLoadSource }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function refreshHistory() {
    setLoading(true);
    setError(null);
    try {
      const data = await listAnalysisRecords(10);
      setRecords(data.items ?? []);
    } catch (err) {
      setError(err.message || "Unable to load history.");
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshHistory();
  }, []);

  async function handleDelete(recordId) {
    try {
      await deleteAnalysisRecord(recordId);
      await refreshHistory();
    } catch (err) {
      setError(err.message || "Unable to delete record.");
    }
  }

  return (
    <div className="card">
      <h2>Recent Analysis History</h2>
      {error && <p className="status status-down">{error}</p>}
      {loading && <p className="muted">Loading saved analyses...</p>}
      {!loading && records.length === 0 && <p className="muted">No saved analyses yet.</p>}
      {!loading && records.length > 0 && (
        <ul className="history-list">
          {records.map((record) => (
            <li key={record.id} className="history-item">
              <div>
                <strong>{record.analysis_type}</strong>
                <div className="muted">
                  {record.created_at} • {record.error_count} errors • {record.status}
                </div>
                <div className="history-summary">{record.summary || "Saved analysis"}</div>
              </div>
              <div className="history-actions">
                <button
                  type="button"
                  className="btn small"
                  onClick={() => onLoadSource?.(record.source)}
                >
                  Load
                </button>
                <button
                  type="button"
                  className="btn small danger"
                  onClick={() => handleDelete(record.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

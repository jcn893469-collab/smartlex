import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../services/api.js";

export default function HealthStatus() {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  const check = useCallback(async () => {
    setState({ loading: true, data: null, error: null });
    try {
      const data = await getHealth();
      setState({ loading: false, data, error: null });
    } catch (err) {
      setState({ loading: false, data: null, error: err.message });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return (
    <div className="card status-card">
      <h2>Backend Status</h2>
      {state.loading && <p className="muted">Checking backend...</p>}
      {state.error && (
        <p className="status status-down">
          Backend unreachable: {state.error}. Make sure it is running on port 8000.
        </p>
      )}
      {state.data && (
        <div>
          <p className="status status-up">● Connected</p>
          <ul className="status-list">
            <li>
              <span>Application</span>
              <strong>{state.data.app}</strong>
            </li>
            <li>
              <span>Version</span>
              <strong>{state.data.version}</strong>
            </li>
            <li>
              <span>Server time (UTC)</span>
              <strong>{state.data.timestamp}</strong>
            </li>
          </ul>
        </div>
      )}
      <button className="btn" onClick={check} disabled={state.loading}>
        Re-check
      </button>
    </div>
  );
}
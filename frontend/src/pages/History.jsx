import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api/client';
import ErrorNotice from '../components/ErrorNotice';
import { GlassCard, Spinner, formatDate } from '../components/primitives';
import { useAuth } from '../state/AuthContext';

export default function History() {
  const { token } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const load = useCallback(
    async (signal) => {
      setLoading(true);
      try {
        const data = await api.listHistory(token, signal);
        setSessions(data.sessions);
        setError(null);
      } catch (err) {
        if (err.name !== 'AbortError') setError(err);
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const remove = async (sessionId) => {
    setDeleting(sessionId);
    try {
      await api.deleteHistoryItem(token, sessionId);
      setSessions((current) => current.filter((item) => item.session_id !== sessionId));
    } catch (err) {
      setError(err);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="container stack-lg">
      <div className="stack" style={{ gap: 8 }}>
        <div className="eyebrow">Your research</div>
        <h1 className="title">History</h1>
        <p className="subtitle">
          Every report you ran while signed in. Only you can see these.
        </p>
      </div>

      <ErrorNotice error={error} />

      <GlassCard>
        {loading ? (
          <div className="row" style={{ color: 'var(--text-muted)' }}>
            <Spinner />
            Loading your sessions…
          </div>
        ) : sessions.length === 0 ? (
          <div className="stack" style={{ gap: 12 }}>
            <p className="secondary">You have not run any research yet.</p>
            <Link to="/" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
              Ask your first question
            </Link>
          </div>
        ) : (
          <div className="stack" style={{ gap: 10 }}>
            {sessions.map((item) => (
              <div className="history-item" key={item.session_id}>
                <Link className="history-item__link" to={`/history/${item.session_id}`}>
                  <div className="history-item__query">{item.query}</div>
                  <div className="history-item__meta">
                    <span>{formatDate(item.created_at)}</span>
                    <span>
                      {item.source_count} source{item.source_count === 1 ? '' : 's'}
                    </span>
                    {item.contradiction_count > 0 && (
                      <span style={{ color: 'var(--warn)' }}>
                        {item.contradiction_count} contradiction
                        {item.contradiction_count === 1 ? '' : 's'}
                      </span>
                    )}
                    {item.is_fallback && <span>fallback mode</span>}
                  </div>
                </Link>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => remove(item.session_id)}
                  disabled={deleting === item.session_id}
                  aria-label={`Delete saved research: ${item.query}`}
                  title="Delete"
                >
                  {deleting === item.session_id ? <Spinner /> : '×'}
                </button>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

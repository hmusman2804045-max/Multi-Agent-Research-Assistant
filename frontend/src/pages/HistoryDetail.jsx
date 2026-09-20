import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import * as api from '../api/client';
import ErrorNotice from '../components/ErrorNotice';
import ReportView from '../components/ReportView';
import { GlassCard, Spinner, formatDate } from '../components/primitives';
import { useAuth } from '../state/AuthContext';

/**
 * A saved report, reopened from history.
 *
 * Stored sessions keep the raw search results and the run metadata, which are mapped
 * here into the same shape a live run produces so one report component renders both.
 */
export default function HistoryDetail() {
  const { sessionId } = useParams();
  const { token } = useAuth();
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        setSession(await api.getHistoryItem(token, sessionId, controller.signal));
        setError(null);
      } catch (err) {
        if (err.name !== 'AbortError') setError(err);
      } finally {
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [token, sessionId]);

  if (loading) {
    return (
      <div className="container">
        <GlassCard>
          <div className="row" style={{ color: 'var(--text-muted)' }}>
            <Spinner />
            Loading saved report…
          </div>
        </GlassCard>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="container stack">
        <ErrorNotice
          error={
            error ||
            new api.ApiError(404, { error: 'not_found', message: 'That report could not be found.' })
          }
        />
        <Link to="/history" className="btn btn-ghost" style={{ alignSelf: 'flex-start' }}>
          Back to history
        </Link>
      </div>
    );
  }

  const metadata = session.metadata || {};
  const usage = { ...(metadata.token_usage || {}) };
  delete usage.model; // the UI reports tokens, not the model's brand name

  const result = {
    query: session.query,
    report: session.report,
    fact_check: session.fact_check,
    is_fallback: Boolean(metadata.is_fallback),
    sources: (session.sources || []).map((source, index) => ({
      index: index + 1,
      title: source.title || 'Untitled source',
      url: source.url || '',
      excerpt: (source.content || '').slice(0, 320),
    })),
    telemetry: {
      total_time_sec: metadata.execution_time_seconds,
      usage,
    },
  };

  return (
    <div className="container stack-lg">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <Link to="/history" className="btn-quiet">
          ← Back to history
        </Link>
        <span className="muted">Saved {formatDate(session.created_at)}</span>
      </div>

      <ReportView result={result} savedToHistory />
    </div>
  );
}

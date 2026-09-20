import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import * as api from '../api/client';
import ErrorNotice from '../components/ErrorNotice';
import ProgressChecklist from '../components/ProgressChecklist';
import ReportView from '../components/ReportView';
import { GlassCard, PIPELINE_STEPS, Tag } from '../components/primitives';
import { useAuth } from '../state/AuthContext';
import { useQuota } from '../state/QuotaContext';

const STEP_IDS = PIPELINE_STEPS.map((step) => step.id);

/**
 * A live research run.
 *
 * Identical for signed-in users and guests: the same stream, the same five steps, the
 * same report. The only difference is that a guest run is not written to history.
 */
export default function Research() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const { token, guestId, isAuthenticated } = useAuth();
  const { refresh: refreshQuota } = useQuota();

  const [completed, setCompleted] = useState({});
  const [activeStep, setActiveStep] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const abortRef = useRef(null);
  const startedFor = useRef(null);

  const run = useCallback(async () => {
    if (!query.trim()) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setCompleted({});
    setActiveStep(STEP_IDS[0]);
    setResult(null);
    setError(null);
    setRunning(true);

    try {
      await api.streamResearch({
        query: query.trim(),
        token,
        guestId,
        signal: controller.signal,
        onEvent: (event, data) => {
          if (event === 'step') {
            setCompleted((current) => ({ ...current, [data.step]: data }));
            setActiveStep(STEP_IDS[data.index] || null);
          } else if (event === 'complete') {
            setResult(data);
            setActiveStep(null);
          } else if (event === 'error') {
            setError(new api.ApiError(0, data));
            setActiveStep(null);
          }
        },
      });
    } catch (err) {
      if (err.name !== 'AbortError') setError(err);
    } finally {
      if (!controller.signal.aborted) {
        setRunning(false);
        refreshQuota();
      }
    }
  }, [query, token, guestId, refreshQuota]);

  // One run per question. A re-render must never re-trigger the pipeline and burn quota.
  // No cleanup abort here on purpose: StrictMode's dev-only remount would otherwise cancel
  // the run it just started, and aborting saves nothing server-side - the backend finishes
  // a run whether or not the client is still listening.
  useEffect(() => {
    const key = `${query}::${token || guestId}`;
    if (startedFor.current === key) return;
    startedFor.current = key;
    run();
  }, [query, token, guestId, run]);

  if (!query.trim()) {
    return (
      <div className="container stack">
        <GlassCard>
          <div className="stack">
            <h1 className="title">No question to research</h1>
            <p className="secondary">Start from the home page to ask something.</p>
            <Link to="/" className="btn btn-ghost" style={{ alignSelf: 'flex-start' }}>
              Back to home
            </Link>
          </div>
        </GlassCard>
      </div>
    );
  }

  const finished = Boolean(result) || Boolean(error);

  return (
    <div className="container stack-lg">
      <div className="stack" style={{ gap: 10 }}>
        <div className="eyebrow">{finished && result ? 'Completed' : 'Researching'}</div>
        <h1 className="title">{query}</h1>
        <div className="row" style={{ gap: 8 }}>
          {!isAuthenticated && <Tag>Guest run · not saved</Tag>}
          {running && !finished && <Tag tone="accent">Five agents run in sequence — this takes a minute or two</Tag>}
        </div>
      </div>

      {error && (
        <div className="stack">
          <ErrorNotice error={error} />
          <div className="row">
            <Link to="/" className="btn btn-ghost">
              Ask something else
            </Link>
            {(error.code === 'token_expired' || error.code === 'invalid_token') && (
              <Link to="/login" className="btn btn-primary">
                Sign in again
              </Link>
            )}
          </div>
        </div>
      )}

      {!result && !error && (
        <GlassCard behind>
          <div className="stack">
            <div className="eyebrow">Pipeline progress</div>
            <ProgressChecklist completed={completed} activeStep={activeStep} finished={finished} />
          </div>
        </GlassCard>
      )}

      {result && (
        <div className="fade-in">
          <ReportView result={result} savedToHistory={result.saved_to_history} />
        </div>
      )}

      {result && (
        <div className="row">
          <Link to="/" className="btn btn-ghost">
            Ask another question
          </Link>
          {result.saved_to_history && (
            <Link to="/history" className="btn btn-ghost">
              View history
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GlassCard, HeroVisual, Notice, PipelineStrip, Tag } from '../components/primitives';
import { useAuth } from '../state/AuthContext';
import { useQuota } from '../state/QuotaContext';

const MAX_QUERY_LENGTH = 500;

export default function Landing() {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { quota } = useQuota();

  const trimmed = query.trim();
  const tooLong = query.length > MAX_QUERY_LENGTH;
  const canSubmit = trimmed.length > 0 && !tooLong;

  const serviceFull = Boolean(quota?.serviceWide?.enabled && quota.serviceWide.exhausted);
  const personalSpent = Boolean(quota?.personal?.exhausted);

  const submit = (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    navigate(`/research?q=${encodeURIComponent(trimmed)}`);
  };

  return (
    <div className="container stack-lg">
      <section className="hero">
        <div className="stack">
          <div className="eyebrow">Multi-agent research</div>
          <h1 className="headline">
            Answers that show
            <br />
            <span className="accent-text">where they came from.</span>
          </h1>
          <p className="subtitle">
            Ask a research question. Five agents plan it, search the live web, distill the
            findings, cross-check them against each other, and write a cited report — with every
            source and every disagreement laid out for you.
          </p>
        </div>
        <HeroVisual />
      </section>

      <GlassCard behind>
        <form className="stack" onSubmit={submit}>
          <div className="field">
            <span className="row" style={{ justifyContent: 'space-between' }}>
              <span className="field__label">Your research question</span>
              <span className={`counter${tooLong ? ' is-over' : ''}`}>
                {query.length}/{MAX_QUERY_LENGTH}
              </span>
            </span>
            <textarea
              className="textarea"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="What are the tradeoffs between solid-state and lithium-ion batteries for grid storage?"
              rows={3}
              aria-label="Your research question"
              aria-describedby="query-help"
            />
            <span className="field__hint" id="query-help">
              {isAuthenticated
                ? 'Reports you run while signed in are saved to your history.'
                : 'Running as a guest — results are not saved. Sign in to keep your history.'}
            </span>
          </div>

          {tooLong && (
            <Notice tone="warn" icon="!">
              Questions are limited to {MAX_QUERY_LENGTH} characters. Trim{' '}
              {query.length - MAX_QUERY_LENGTH} character
              {query.length - MAX_QUERY_LENGTH === 1 ? '' : 's'} to continue.
            </Notice>
          )}

          {serviceFull && (
            <Notice tone="warn" title="The service is at capacity today" icon="!">
              Every account shares one daily research budget and it is spent for today. Research
              becomes available again after the shared reset.
            </Notice>
          )}

          {!serviceFull && personalSpent && (
            <Notice tone="warn" title="You have used your searches for today" icon="!">
              Your personal daily quota is spent. It resets at 00:00 UTC.
            </Notice>
          )}

          <div className="row" style={{ justifyContent: 'space-between' }}>
            <PipelineStrip />
            <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
              Start research
            </button>
          </div>
        </form>
      </GlassCard>

      <section className="grid-2">
        <GlassCard>
          <div className="stack" style={{ gap: 10 }}>
            <Tag tone="accent">Cross-checked</Tag>
            <h2 className="title" style={{ fontSize: '1.05rem' }}>
              Disagreements are shown, not smoothed over
            </h2>
            <p className="secondary">
              When retrieved sources contradict each other, the report says so explicitly instead
              of quietly picking one. Cross-referencing is not ground-truth verification, and the
              report does not pretend otherwise.
            </p>
          </div>
        </GlassCard>
        <GlassCard>
          <div className="stack" style={{ gap: 10 }}>
            <Tag>Takes a minute or two</Tag>
            <h2 className="title" style={{ fontSize: '1.05rem' }}>
              You can watch it work
            </h2>
            <p className="secondary">
              Five sequential agents means real latency — a full run is typically a minute or two,
              not instant. Each step reports back as it finishes, so you see the sub-questions, the
              source count and the contradiction count as they land, not a blank screen.
            </p>
          </div>
        </GlassCard>
      </section>
    </div>
  );
}

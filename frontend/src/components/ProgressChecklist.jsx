import { PIPELINE_STEPS } from './primitives';

const STEP_LABELS = {
  planning: 'Planning the research',
  searching: 'Searching sources',
  summarizing: 'Summarizing findings',
  fact_checking: 'Cross-checking claims',
  writing: 'Writing the report',
};

/**
 * The five-step checklist, driven live by the SSE stream.
 *
 * Completed steps carry a check and their result detail, the active step carries an
 * animated indicator, and upcoming steps sit behind ghosted glass rather than being
 * greyed-out text — they are pending, not disabled.
 */
export default function ProgressChecklist({ completed, activeStep, finished }) {
  return (
    <ol className="checklist" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {PIPELINE_STEPS.map((step) => {
        const done = completed[step.id];
        const isActive = !done && step.id === activeStep && !finished;
        const state = done ? 'is-done' : isActive ? 'is-active' : 'is-upcoming';

        return (
          <li key={step.id} className={`check-step ${state}`}>
            <span className="check-step__marker" aria-hidden="true">
              {done ? '✓' : isActive ? <span className="pulse-ring" /> : ''}
            </span>
            <div className="check-step__body">
              <div className="check-step__name">
                <span className="check-step__label">{STEP_LABELS[step.id]}</span>
                {done && <span className="muted mono">{done.elapsed_sec}s</span>}
                {isActive && <span className="muted">working…</span>}
              </div>
              {done && <StepDetail stepId={step.id} payload={done.payload} />}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepDetail({ stepId, payload }) {
  if (!payload) return null;

  if (stepId === 'planning') {
    const subQueries = payload.sub_queries || [];
    if (!subQueries.length) return null;
    return (
      <>
        <div className="check-step__detail">
          Broke the question into {subQueries.length} sub-question{subQueries.length === 1 ? '' : 's'}:
        </div>
        <ul className="check-step__list">
          {subQueries.map((sub) => (
            <li key={sub}>{sub}</li>
          ))}
        </ul>
      </>
    );
  }

  if (stepId === 'searching') {
    return (
      <div className="check-step__detail">
        Retrieved {payload.source_count} unique source{payload.source_count === 1 ? '' : 's'}.
      </div>
    );
  }

  if (stepId === 'summarizing') {
    return (
      <div className="check-step__detail">
        Extracted {payload.claim_count} claim{payload.claim_count === 1 ? '' : 's'} across{' '}
        {payload.summarized_source_count} source{payload.summarized_source_count === 1 ? '' : 's'}.
      </div>
    );
  }

  if (stepId === 'fact_checking') {
    const count = payload.contradiction_count ?? 0;
    return (
      <div className="check-step__detail">
        {count === 0
          ? 'No contradictions found between sources.'
          : `Flagged ${count} contradiction${count === 1 ? '' : 's'} between sources.`}
      </div>
    );
  }

  return null;
}

/**
 * Small shared presentational primitives: glass surfaces, notices, tags, fields and
 * the understated pipeline strip. Everything here shares one visual language so no
 * screen has to invent its own.
 */

/** A glass card. `behind` adds a translucent secondary panel peeking out from under it. */
export function GlassCard({ behind = false, className = '', children, ...rest }) {
  return (
    <div className={`glass glass-pad layered ${className}`} {...rest}>
      {behind && <div className="glass-behind" aria-hidden="true" />}
      {children}
    </div>
  );
}

export function Field({ label, hint, children, trailing }) {
  return (
    <label className="field">
      <span className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
        <span className="field__label">{label}</span>
        {trailing}
      </span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  );
}

/**
 * Non-alarming inline messaging. `warn` (muted amber) is reserved for genuine warning
 * signals — contradictions and exhausted capacity — never for ordinary validation.
 */
export function Notice({ tone = 'neutral', title, children, icon }) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'warn' ? 'alert' : 'status'}>
      {icon && (
        <span className="notice__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <div>
        {title && <div className="notice__title">{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function Tag({ tone = 'neutral', children }) {
  return <span className={`tag${tone === 'neutral' ? '' : ` tag--${tone}`}`}>{children}</span>;
}

export const PIPELINE_STEPS = [
  { id: 'planning', label: 'Plan' },
  { id: 'searching', label: 'Search' },
  { id: 'summarizing', label: 'Summarize' },
  { id: 'fact_checking', label: 'Fact-Check' },
  { id: 'writing', label: 'Write' },
];

/** The understated five-step strip shown on the landing page. */
export function PipelineStrip() {
  return (
    <div className="pipeline-strip" aria-label="Research pipeline: Plan, Search, Summarize, Fact-Check, Write">
      {PIPELINE_STEPS.map((step, index) => (
        <span key={step.id} className="row" style={{ gap: 8 }}>
          {index > 0 && <span className="pipeline-strip__sep" aria-hidden="true" />}
          <span className="pipeline-strip__step">
            <span className="pipeline-strip__dot" aria-hidden="true" />
            {step.label}
          </span>
        </span>
      ))}
    </div>
  );
}

/** Abstract dimensional centrepiece: nested CSS-3D rings and layered plates. */
export function HeroVisual() {
  return (
    <div className="hero__visual" aria-hidden="true">
      <div className="prism">
        <span className="prism__ring" />
        <span className="prism__ring" />
        <span className="prism__ring" />
        <span className="prism__plate" />
        <span className="prism__plate" />
        <span className="prism__plate" />
        <span className="prism__core" />
      </div>
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

/** Formats a seconds-to-reset countdown as compact human text. */
export function formatCountdown(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return 'shortly';
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function domainOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url || '';
  }
}

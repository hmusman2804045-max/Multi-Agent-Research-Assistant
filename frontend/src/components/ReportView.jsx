import { Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { GlassCard, Notice, Tag, domainOf } from './primitives';

/**
 * A finished research report: the markdown body with live [n] citation markers, the
 * numbered sources panel they jump to, the contradictions callout, and a collapsible
 * telemetry footer.
 */
export default function ReportView({ result, savedToHistory }) {
  const contradictions = result.fact_check?.contradictions || [];
  const sources = result.sources || [];
  // The writer occasionally returns nothing usable. Saying so is better than presenting
  // an empty card as though it were the finished report; the retrieved sources below are
  // still real and still worth showing.
  const hasReport = Boolean((result.report || '').trim());

  return (
    <div className="stack-lg">
      <GlassCard>
        <div className="stack">
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div className="eyebrow">Research report</div>
              <h1 className="title" style={{ marginTop: 6 }}>
                {result.query}
              </h1>
            </div>
            <div className="row" style={{ gap: 6 }}>
              {savedToHistory && <Tag tone="accent">Saved to history</Tag>}
              {result.is_fallback && <Tag tone="warn">Fallback mode</Tag>}
            </div>
          </div>

          {result.is_fallback && (
            <p className="muted">
              One of the agents fell back to its simpler backup method for this run, so parts of
              this report are less detailed than usual. The findings and sources below are still
              the real result of the run.
            </p>
          )}

          <hr className="divider" />

          {hasReport ? (
            <div className="report">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {result.report}
              </ReactMarkdown>
            </div>
          ) : (
            <Notice tone="warn" title="The write-up came back empty" icon="!">
              The first four agents finished, but the writer returned no text for this run. The
              sources it gathered are listed below, and running the question again usually
              produces a full report.
            </Notice>
          )}
        </div>
      </GlassCard>

      {contradictions.length > 0 && <ContradictionsCallout contradictions={contradictions} />}

      {sources.length > 0 && <SourcesPanel sources={sources} />}

      <TelemetryFooter telemetry={result.telemetry} />
    </div>
  );
}

/* ===== Contradictions ======================================================= */

function ContradictionsCallout({ contradictions }) {
  return (
    <Notice tone="warn" title="Contradictions & discrepancies" icon="!">
      <div className="stack" style={{ gap: 12, marginTop: 6 }}>
        <p className="muted">
          These sources disagree with each other. The fact-checker cross-references what sources
          claim; it cannot decide which of them is right.
        </p>
        {contradictions.map((item, index) => (
          <div key={`${item.topic}-${index}`}>
            <div style={{ color: 'var(--warn)', fontSize: '0.88rem' }}>{item.topic}</div>
            <div className="secondary">{item.conflict}</div>
            {item.conflicting_sources?.length > 0 && (
              <div className="muted" style={{ marginTop: 4 }}>
                Sources{' '}
                {item.conflicting_sources.map((id, i) => (
                  <Fragment key={id}>
                    {i > 0 && ', '}
                    <a className="citation" href={`#source-${id}`}>
                      {id}
                    </a>
                  </Fragment>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Notice>
  );
}

/* ===== Sources ============================================================== */

function SourcesPanel({ sources }) {
  return (
    <GlassCard>
      <div className="stack">
        <div>
          <div className="eyebrow">Sources</div>
          <p className="muted" style={{ marginTop: 4 }}>
            {sources.length} source{sources.length === 1 ? '' : 's'} retrieved for this report.
          </p>
        </div>
        <div className="sources">
          {sources.map((source) => (
            <div className="source" key={source.index} id={`source-${source.index}`}>
              <span className="source__index">{source.index}</span>
              <div className="source__body">
                <a
                  className="source__title"
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                >
                  {source.title || 'Untitled source'}
                </a>
                <span className="source__domain">{domainOf(source.url)}</span>
                {source.excerpt && <p className="source__excerpt">{source.excerpt}…</p>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </GlassCard>
  );
}

/* ===== Telemetry ============================================================ */

function TelemetryFooter({ telemetry }) {
  if (!telemetry) return null;
  const usage = telemetry.usage || {};

  // Per-step timings are only available on a live run; a report reloaded from history
  // carries the total and the token count, so absent rows are simply dropped.
  const rows = [
    ['Planning', telemetry.planning_time_sec],
    ['Search', telemetry.search_time_sec],
    ['Summarizing', telemetry.summarization_time_sec],
    ['Fact-checking', telemetry.fact_check_time_sec],
    ['Writing', telemetry.synthesis_time_sec],
    ['Total time', telemetry.total_time_sec],
  ]
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([label, value]) => [label, `${value}s`]);

  rows.push(['Tokens used', (usage.total_tokens ?? 0).toLocaleString()]);

  return (
    <details className="telemetry glass glass-pad" style={{ padding: '14px 18px' }}>
      <summary>
        Run details · {telemetry.total_time_sec}s · {(usage.total_tokens ?? 0).toLocaleString()} tokens
      </summary>
      <div className="telemetry__grid">
        {rows.map(([label, value]) => (
          <div className="telemetry__item" key={label}>
            <span>{label}</span>
            <span>{value}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

/* ===== Markdown rendering =================================================== */

const CITATION_PATTERN = /(\[\d{1,3}\])/g;

/**
 * Turns inline [1][2] markers in the report body into anchors that scroll down to the
 * matching numbered entry in the Sources panel.
 */
function linkCitations(children) {
  return children.map((child, index) => {
    if (typeof child !== 'string') return <Fragment key={index}>{child}</Fragment>;

    const parts = child.split(CITATION_PATTERN);
    return (
      <Fragment key={index}>
        {parts.map((part, partIndex) => {
          const match = /^\[(\d{1,3})\]$/.exec(part);
          if (!match) return <Fragment key={partIndex}>{part}</Fragment>;
          return (
            <a
              key={partIndex}
              className="citation"
              href={`#source-${match[1]}`}
              aria-label={`Jump to source ${match[1]}`}
            >
              {match[1]}
            </a>
          );
        })}
      </Fragment>
    );
  });
}

function withCitations(element) {
  const Element = element;
  return function Renderer({ children, ...rest }) {
    return <Element {...rest}>{linkCitations(Array.isArray(children) ? children : [children])}</Element>;
  };
}

const markdownComponents = {
  p: withCitations('p'),
  li: withCitations('li'),
  td: withCitations('td'),
  a: ({ children, href, ...rest }) => (
    <a {...rest} href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  ),
};

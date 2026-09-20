import { useEffect, useState } from 'react';
import { useQuota } from '../state/QuotaContext';
import { formatCountdown } from './primitives';

/**
 * Persistent quota readout in the header.
 *
 * Shows the reader's own allocation. If the separate service-wide pool is empty, that
 * takes over the widget with its own wording — it means something different from the
 * reader having spent their personal searches, and conflating the two would mislead.
 */
export default function QuotaWidget() {
  const { quota, loading } = useQuota();
  const [countdown, setCountdown] = useState(null);

  useEffect(() => {
    if (!quota) return undefined;
    setCountdown(quota.personal.seconds_to_daily_reset);
    const timer = window.setInterval(() => {
      setCountdown((current) => (current === null ? null : Math.max(0, current - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [quota]);

  if (loading || !quota) {
    return <div className="quota muted">Checking quota…</div>;
  }

  const { personal, serviceWide } = quota;

  if (serviceWide.enabled && serviceWide.exhausted) {
    return (
      <div className="quota">
        <div className="quota__line">
          <span style={{ color: 'var(--warn)' }}>Service at capacity today</span>
        </div>
        <div className="quota__bar">
          <div className="quota__fill is-full" style={{ width: '100%' }} />
        </div>
        <span className="muted">Shared capacity resets in {formatCountdown(countdown)}</span>
      </div>
    );
  }

  const used = personal.daily_used;
  const limit = personal.daily_limit;
  const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

  return (
    <div className="quota">
      <div className="quota__line">
        <span className="mono">
          {used} of {limit} searches used today
        </span>
      </div>
      <div className="quota__bar">
        <div
          className={`quota__fill${personal.exhausted ? ' is-full' : ''}`}
          style={{ width: `${percent}%` }}
          role="progressbar"
          aria-valuenow={used}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-label="Daily searches used"
        />
      </div>
      <span className="muted">
        {personal.exhausted ? 'Resets' : 'Quota resets'} in {formatCountdown(countdown)}
      </span>
    </div>
  );
}

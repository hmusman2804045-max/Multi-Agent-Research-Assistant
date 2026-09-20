import { useEffect, useState } from 'react';
import { Notice, formatCountdown } from './primitives';

/**
 * Renders an ApiError with wording that matches what the backend actually enforced.
 *
 * The distinctions matter to the reader and are kept strictly apart:
 *   personal daily cap   - this account has spent its own searches for the day.
 *   service-wide cap     - the shared pool is empty; nobody can run research right now.
 *   burst (RPM) limit    - a short cool-off, measured in seconds, not a quota at all.
 *   account locked       - too many failed *login* attempts, nothing more sinister.
 * Styling stays on the same muted palette as the rest of the app; the amber tone is used
 * only where something is genuinely blocked, never as an alarm colour.
 */
export default function ErrorNotice({ error, onRetry }) {
  const [countdown, setCountdown] = useState(null);

  const initialCountdown = error?.retryAfterSeconds ?? error?.remainingLockoutSeconds ?? null;

  useEffect(() => {
    if (initialCountdown === null) {
      setCountdown(null);
      return undefined;
    }
    setCountdown(initialCountdown);
    const timer = window.setInterval(() => {
      setCountdown((current) => (current === null ? null : Math.max(0, current - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [initialCountdown, error]);

  if (!error) return null;

  const { tone, title, body } = describe(error, countdown);

  return (
    <Notice tone={tone} title={title} icon={tone === 'warn' ? '!' : '·'}>
      <div className="stack" style={{ gap: 8 }}>
        <p>{body}</p>
        {error.message && error.message !== body && <p className="muted">{error.message}</p>}
        {onRetry && countdown === 0 && (
          <button type="button" className="btn-quiet" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </Notice>
  );
}

function describe(error, countdown) {
  const wait = countdown === null ? null : formatCountdown(countdown);

  if (error.code === 'daily_limit_exceeded' && error.capScope === 'global') {
    return {
      tone: 'warn',
      title: 'The service is at capacity today',
      body: `Every account shares one daily research budget, and it is spent for today. Research becomes available again after the shared reset${wait ? ` in ${wait}` : ''}.`,
    };
  }

  if (error.code === 'daily_limit_exceeded') {
    return {
      tone: 'warn',
      title: 'You have used your searches for today',
      body: `Your personal daily research quota is spent. It resets at 00:00 UTC${wait ? `, in ${wait}` : ''}.`,
    };
  }

  if (error.code === 'burst_rate_limit_exceeded') {
    return {
      tone: 'neutral',
      title: 'Slow down for a moment',
      body: `You are sending research requests faster than the per-minute limit allows. You can try again${wait ? ` in ${wait}` : ' shortly'}.`,
    };
  }

  if (error.code === 'password_reset_rate_limit_exceeded') {
    return {
      tone: 'neutral',
      title: 'Too many reset requests',
      body: `Password reset requests are limited per hour. You can request another${wait ? ` in ${wait}` : ' shortly'}.`,
    };
  }

  if (error.code === 'account_locked') {
    return {
      tone: 'warn',
      title: 'Account temporarily locked',
      body: `Too many failed login attempts for this account. Sign-in reopens${wait ? ` in ${wait}` : ' shortly'}, or reset your password to unlock it now.`,
    };
  }

  if (error.code === 'invalid_credentials' || error.code === 'user_not_found') {
    return {
      tone: 'neutral',
      title: 'Sign-in failed',
      body: 'That username and password combination did not match an account.',
    };
  }

  if (error.code === 'token_expired') {
    return {
      tone: 'neutral',
      title: 'Session expired',
      body: 'Your session has expired. Sign in again to continue.',
    };
  }

  if (error.code === 'invalid_token') {
    return {
      tone: 'neutral',
      title: 'That link is no longer valid',
      body: 'Reset links work once and expire after 15 minutes. Request a new one to continue.',
    };
  }

  if (error.code === 'user_already_exists') {
    return { tone: 'neutral', title: 'Could not create the account', body: error.message };
  }

  if (error.code === 'weak_password') {
    return { tone: 'neutral', title: 'Password too short', body: error.message };
  }

  if (error.code === 'network_error') {
    return {
      tone: 'neutral',
      title: 'Could not reach the service',
      body: 'The research service did not respond. Check your connection and try again.',
    };
  }

  return { tone: 'neutral', title: 'Something went wrong', body: error.message };
}

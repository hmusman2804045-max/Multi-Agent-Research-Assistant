import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import * as api from '../api/client';
import ErrorNotice from '../components/ErrorNotice';
import { Field, GlassCard, Notice, Spinner } from '../components/primitives';

/** Step two of the reset flow: the token arrives in the URL, or is pasted by hand. */
export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [token, setToken] = useState(() => searchParams.get('token') || '');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const mismatch = confirmation.length > 0 && password !== confirmation;
  const canSubmit = token.trim() && password.length >= 8 && !mismatch;

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.resetPassword(token.trim(), password);
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="container stack-lg" style={{ maxWidth: 560 }}>
      <div className="stack" style={{ alignItems: 'center', textAlign: 'center' }}>
        <div className="eyebrow">Step 2 of 2 · Reset</div>
        <h1 className="title">Choose a new password</h1>
      </div>

      <GlassCard behind>
        {done ? (
          <div className="stack">
            <Notice tone="accent" title="Password updated" icon="✓">
              You can now sign in with your new password. Any login lockout on the account has
              been cleared.
            </Notice>
            <button type="button" className="btn btn-primary" onClick={() => navigate('/login')}>
              Go to sign in
            </button>
          </div>
        ) : (
          <form className="stack" onSubmit={submit}>
            <Field
              label="Reset token"
              hint="Valid for 15 minutes and usable once. Opening the link from your email fills this in automatically."
            >
              <input
                className="input"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                spellCheck="false"
                autoCapitalize="none"
                required
              />
            </Field>

            <Field label="New password" hint="At least 8 characters.">
              <input
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </Field>

            <Field label="Confirm new password">
              <input
                className="input"
                type="password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="new-password"
                required
              />
            </Field>

            {mismatch && (
              <Notice tone="neutral" icon="·">
                The two passwords do not match yet.
              </Notice>
            )}

            <ErrorNotice error={error} />

            <button type="submit" className="btn btn-primary btn-block" disabled={busy || !canSubmit}>
              {busy && <Spinner />}
              Set new password
            </button>

            <div className="row" style={{ justifyContent: 'center', gap: 16 }}>
              <Link to="/forgot-password" className="btn-quiet">
                Request a new token
              </Link>
              <Link to="/login" className="btn-quiet">
                Back to sign in
              </Link>
            </div>
          </form>
        )}
      </GlassCard>
    </div>
  );
}

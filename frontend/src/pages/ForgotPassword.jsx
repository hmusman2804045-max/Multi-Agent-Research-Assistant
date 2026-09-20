import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import ErrorNotice from '../components/ErrorNotice';
import { Field, GlassCard, Notice, Spinner } from '../components/primitives';

/**
 * Two-step password reset.
 *
 * Step one requests the link. The confirmation is deliberately generic and identical
 * whether or not the account exists, matching what the backend guarantees — the UI must
 * not leak through wording what the API refuses to leak through timing.
 */
export default function ForgotPassword() {
  const [identifier, setIdentifier] = useState('');
  const [sentMessage, setSentMessage] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { message } = await api.forgotPassword(identifier.trim());
      setSentMessage(message);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="container stack-lg" style={{ maxWidth: 560 }}>
      <div className="stack" style={{ alignItems: 'center', textAlign: 'center' }}>
        <div className="eyebrow">Step 1 of 2 · Request</div>
        <h1 className="title">Reset your password</h1>
      </div>

      <GlassCard behind>
        {sentMessage ? (
          <div className="stack">
            <Notice tone="accent" title="Request received" icon="·">
              {sentMessage}
            </Notice>
            <p className="secondary">
              If a reset email arrives, it carries a token that is valid for 15 minutes and can be
              used once. Open the link from the email, or paste the token on the next step.
            </p>
            <div className="row">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/reset-password')}
              >
                I have a token
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  setSentMessage(null);
                  setIdentifier('');
                }}
              >
                Send to a different account
              </button>
            </div>
          </div>
        ) : (
          <form className="stack" onSubmit={submit}>
            <Field
              label="Username or email"
              hint="Enter whichever you registered with."
            >
              <input
                className="input"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck="false"
                required
              />
            </Field>

            <ErrorNotice error={error} />

            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={busy || !identifier.trim()}
            >
              {busy && <Spinner />}
              Send reset link
            </button>

            <div className="row" style={{ justifyContent: 'center', gap: 16 }}>
              <Link to="/login" className="btn-quiet">
                Back to sign in
              </Link>
              <Link to="/reset-password" className="btn-quiet">
                I already have a token
              </Link>
            </div>
          </form>
        )}
      </GlassCard>
    </div>
  );
}

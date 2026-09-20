import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import ErrorNotice from '../components/ErrorNotice';
import { Field, GlassCard, Spinner } from '../components/primitives';
import { useAuth } from '../state/AuthContext';

/**
 * Combined sign in / create account screen.
 *
 * The inactive card sits ghosted behind the active one rather than disappearing, so the
 * two modes read as one layered surface instead of two separate pages.
 */
export default function Auth({ mode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn, signUp } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const isRegister = mode === 'register';
  const redirectTo = location.state?.from || '/';

  const switchMode = (nextMode) => {
    setError(null);
    navigate(nextMode === 'register' ? '/register' : '/login', {
      replace: true,
      state: location.state,
    });
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (isRegister) await signUp(username.trim(), password, email.trim() || null);
      else await signIn(username.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="container stack-lg" style={{ maxWidth: 560 }}>
      <div className="stack" style={{ alignItems: 'center', textAlign: 'center' }}>
        <div className="eyebrow">{isRegister ? 'Create an account' : 'Welcome back'}</div>
        <h1 className="title">
          {isRegister ? 'Keep every report you run' : 'Sign in to your research history'}
        </h1>
      </div>

      <div className="row" style={{ justifyContent: 'center' }}>
        <div className="tabs" role="tablist" aria-label="Sign in or create an account">
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            className={!isRegister ? 'is-active' : ''}
            onClick={() => switchMode('login')}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            className={isRegister ? 'is-active' : ''}
            onClick={() => switchMode('register')}
          >
            Register
          </button>
        </div>
      </div>

      <GlassCard behind>
        <form className="stack" onSubmit={submit}>
          <Field label="Username">
            <input
              className="input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck="false"
              required
            />
          </Field>

          <Field
            label="Password"
            hint={isRegister ? 'At least 8 characters.' : undefined}
          >
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              minLength={isRegister ? 8 : undefined}
              required
            />
          </Field>

          {isRegister && (
            <Field
              label="Email (optional)"
              hint="Only used to send a password reset link if you ever need one."
            >
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
              />
            </Field>
          )}

          <ErrorNotice error={error} />

          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy && <Spinner />}
            {isRegister ? 'Create account' : 'Sign in'}
          </button>

          {!isRegister && (
            <div className="row" style={{ justifyContent: 'center' }}>
              <Link to="/forgot-password" className="btn-quiet">
                Forgot password?
              </Link>
            </div>
          )}
        </form>
      </GlassCard>

      <div className="stack" style={{ alignItems: 'center', gap: 10 }}>
        <Link to="/" className="btn btn-ghost">
          Continue as guest
        </Link>
        <p className="muted" style={{ textAlign: 'center', maxWidth: '44ch' }}>
          Guest research runs exactly the same, and is still rate limited, but nothing is saved —
          close the tab and the report is gone.
        </p>
      </div>
    </div>
  );
}

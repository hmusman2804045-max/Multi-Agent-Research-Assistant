import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import AmbientBackground from './components/AmbientBackground';
import QuotaWidget from './components/QuotaWidget';
import Auth from './pages/Auth';
import ForgotPassword from './pages/ForgotPassword';
import History from './pages/History';
import HistoryDetail from './pages/HistoryDetail';
import Landing from './pages/Landing';
import Research from './pages/Research';
import ResetPassword from './pages/ResetPassword';
import { useAuth } from './state/AuthContext';

export default function App() {
  return (
    <>
      <AmbientBackground />
      <div className="shell">
        <Header />
        <main className="page">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/research" element={<Research />} />
            <Route path="/login" element={<Auth mode="login" />} />
            <Route path="/register" element={<Auth mode="register" />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route
              path="/history"
              element={
                <RequireAuth>
                  <History />
                </RequireAuth>
              }
            />
            <Route
              path="/history/:sessionId"
              element={
                <RequireAuth>
                  <HistoryDetail />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </>
  );
}

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

function Header() {
  const { isAuthenticated, user, signOut } = useAuth();

  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <NavLink to="/" className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <path
                d="M1.5 6.4L4.4 9.3L10.5 3"
                stroke="#7FA795"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          Research Assistant
        </NavLink>

        <span className="spacer" />

        <QuotaWidget />

        <nav className="nav">
          {isAuthenticated ? (
            <>
              <NavLink to="/history">History</NavLink>
              <button type="button" onClick={signOut} title={`Signed in as ${user?.userId}`}>
                Sign out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Sign in</NavLink>
              <NavLink to="/register">Register</NavLink>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="container" style={{ padding: '28px 16px 36px' }}>
      <p className="muted">
        Sources are cross-referenced against each other, not against ground truth. Treat flagged
        contradictions as a prompt to check the originals yourself.
      </p>
    </footer>
  );
}

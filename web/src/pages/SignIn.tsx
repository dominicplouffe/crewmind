/** The sign-in page. */
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { post } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote, Field } from "../components/common";
import { LogoMark } from "../ui/Logo";
import { t } from "../strings";

export function SignIn(): JSX.Element {
  const { person, reload } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; notice?: string } | null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (person) return <Navigate to={state?.from ?? "/"} replace />;

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/v1/auth/login", { email, password });
      await reload();
      navigate(state?.from ?? "/", { replace: true });
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="center-page">
      <div className="card auth-card">
        <div className="auth-brand">
          <LogoMark size={40} />
        </div>
        <h1>{t.signIn.title}</h1>
        {state?.notice ? (
          <p className="note" role="status">
            {state.notice}
          </p>
        ) : null}
        <form onSubmit={(event) => void submit(event)}>
          <Field label={t.signIn.email} htmlFor="signin-email">
            <input
              id="signin-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label={t.signIn.password} htmlFor="signin-password">
            <input
              id="signin-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <ErrorNote error={error} />
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? t.signIn.busy : t.signIn.submit}
          </button>
        </form>
        <p className="quiet">{t.signIn.help}</p>
      </div>
    </main>
  );
}

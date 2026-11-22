/** Sets a password from a setup or reset link, then sends the person to sign in. */
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { post } from "../api/client";
import { ErrorNote, Field } from "../components/common";
import { t } from "../strings";

export function AcceptLink(): JSX.Element {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [mismatch, setMismatch] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    if (password !== again) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setBusy(true);
    try {
      await post("/v1/auth/use_link", { link: token, password });
      navigate("/signin", { replace: true, state: { notice: t.accept.done } });
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="center-page">
      <div className="card">
        <h1>{t.accept.title}</h1>
        <p className="quiet">{t.accept.intro}</p>
        <form onSubmit={(event) => void submit(event)}>
          <Field label={t.accept.password} htmlFor="accept-password">
            <input
              id="accept-password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field label={t.accept.again} htmlFor="accept-again">
            <input
              id="accept-again"
              type="password"
              autoComplete="new-password"
              required
              value={again}
              onChange={(event) => setAgain(event.target.value)}
            />
          </Field>
          {mismatch ? (
            <p className="note note-error" role="alert">
              {t.accept.mismatch}
            </p>
          ) : null}
          <ErrorNote error={error} />
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? t.accept.busy : t.accept.submit}
          </button>
        </form>
      </div>
    </main>
  );
}

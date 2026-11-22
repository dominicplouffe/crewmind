/** Asks the signed-in person whether an AI client may act for them, and for which permissions. */
import { useEffect, useMemo, useState } from "react";
import { post } from "../api/client";
import { Empty, ErrorNote } from "../components/common";
import { denialUrl, readApproval } from "../lib/oauth";
import { t } from "../strings";

export function OAuthApprove({ hash }: { hash: string }): JSX.Element {
  const words = t.oauth;
  const request = useMemo(() => readApproval(hash), [hash]);
  const [ticked, setTicked] = useState<string[]>(request.scopes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    document.title = words.pageTitle;
    return () => {
      document.title = t.app.name;
    };
  }, [words.pageTitle]);

  const approve = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const approved = await post("/v1/oauth/approve", {
        client_id: request.clientId,
        redirect_uri: request.redirectUri,
        // Only scopes that were asked for, in the order they were asked.
        scopes: request.scopes.filter((scope) => ticked.includes(scope)),
        code_challenge: request.codeChallenge,
        code_challenge_method: request.codeChallengeMethod,
        resource: request.resource,
        state: request.state,
      });
      window.location.assign(approved.redirect_to);
    } catch (reason) {
      setError(reason);
      setBusy(false);
    }
  };

  const deny = (): void => {
    window.location.assign(denialUrl(request.redirectUri, request.state) ?? "/");
  };

  const complete = request.clientId !== "" && request.redirectUri !== "";
  return (
    <div className="page">
      <main className="content narrow">
        <h1>{words.title}</h1>
        {!complete ? (
          <>
            <Empty title={words.incompleteTitle} next={words.incompleteNext} />
            <a href="/">{words.home}</a>
          </>
        ) : (
          <div className="card" data-testid="oauth-approve">
            <p>{words.intro}</p>
            <dl className="pairs">
              <div>
                <dt>{words.client}</dt>
                <dd data-testid="oauth-client">{request.clientId}</dd>
              </div>
              <div>
                <dt>{words.sendsBack}</dt>
                <dd data-testid="oauth-redirect">{request.redirectUri}</dd>
              </div>
            </dl>
            <fieldset className="plan-fieldset">
              <legend>{words.scopesLegend}</legend>
              {request.scopes.length === 0 ? <p className="quiet">{words.noneAsked}</p> : null}
              {request.scopes.map((scope) => {
                const known = words.scopes[scope];
                return (
                  <p key={scope}>
                    <input
                      type="checkbox"
                      id={`scope-${scope}`}
                      checked={ticked.includes(scope)}
                      aria-describedby={`scope-${scope}-allows`}
                      onChange={(event) =>
                        setTicked((old) => (event.target.checked ? [...old, scope] : old.filter((each) => each !== scope)))
                      }
                    />{" "}
                    <label htmlFor={`scope-${scope}`}>{known?.name ?? scope}</label>
                    <span className="quiet" id={`scope-${scope}-allows`}>
                      {" "}
                      {known?.allows ?? words.unknownScope}
                    </span>
                  </p>
                );
              })}
            </fieldset>
            {ticked.length === 0 ? <p className="quiet">{words.noneTicked}</p> : null}
            <ErrorNote error={error} />
            <div className="row wrap">
              <button
                type="button"
                className="button primary"
                disabled={busy || ticked.length === 0}
                onClick={() => void approve()}
              >
                {busy ? words.approving : words.approve}
              </button>
              <button type="button" className="button" disabled={busy} onClick={deny}>
                {words.deny}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

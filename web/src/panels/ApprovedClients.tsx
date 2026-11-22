/** The AI clients the person approved to act for them, each with a way to revoke it. */
import { useState } from "react";
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { useAct } from "./memory/parts";
import { ActionButton, Confirm } from "./plan/parts";

const noop = (): void => undefined;

export function ApprovedClients(): JSX.Element {
  const words = t.oauth.clients;
  const clients = useLoad(() => get("/v1/oauth/clients"), []);
  const [asking, setAsking] = useState<string | null>(null);
  const act = useAct(noop);
  const items = clients.data?.items ?? [];
  const scopeNames = (scopes: string[]): string => scopes.map((scope) => t.oauth.scopes[scope]?.name ?? scope).join(", ");

  return (
    <section aria-labelledby="approved-clients-title" data-testid="approved-clients">
      <h3 id="approved-clients-title">{words.title}</h3>
      <ErrorNote error={clients.error ?? act.error} />
      {clients.data && items.length === 0 ? <p className="quiet">{words.empty}</p> : null}
      <ul className="settings plain" aria-label={words.listLabel}>
        {items.map((client) => (
          <li key={client.grant_id} data-testid="approved-client">
            <div className="setting-line">
              <span className="setting-name">{client.client_name}</span>
              <ActionButton
                label={words.revoke}
                of={client.client_name}
                disabled={act.busy}
                onClick={() => setAsking(client.grant_id)}
              />
            </div>
            <p className="quiet">
              {words.scopes(scopeNames(client.scopes))} · {words.since(formatDateTime(client.since))}
            </p>
            {asking === client.grant_id ? (
              <Confirm
                question={words.confirm(client.client_name)}
                yes={words.confirmYes}
                busy={act.busy}
                onCancel={() => setAsking(null)}
                onYes={() =>
                  void act.run(async () => {
                    clients.setData(await post("/v1/oauth/revoke", { grant_id: client.grant_id }));
                    setAsking(null);
                  })
                }
              />
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

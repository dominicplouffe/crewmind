/**
 * The Founder's model (LLM-14, FND-2): whether it is ready, which key it uses and at what quality.
 * Opened with `?return=/draft/<id>`, it offers the way back to the conversation once saved.
 */
import { Link, useSearchParams } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { metaOf } from "../lib/settingsMeta";
import { useLoad } from "../lib/useLoad";
import { founderReadyWith, usableModelKeys } from "../onboarding/useSetupStatus";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { FounderForm } from "./FounderForm";
import { safeReturn } from "./paths";

export function FounderSection(): JSX.Element {
  const words = settingsWords.founder;
  const [params] = useSearchParams();
  const back = safeReturn(params.get("return"));
  const data = useLoad(() => Promise.all([get("/v1/settings/show_install"), get("/v1/credentials/list")]), []);
  const [install, credentials] = data.data ?? [null, null];
  const keys = usableModelKeys(credentials?.items ?? []);
  const value = (name: string): string => String(install?.items.find((item) => item.name === name)?.value ?? "");
  const credential = value("founder.credential");
  const modelClass = value("founder.model_class");
  const ready = founderReadyWith(credential, keys);
  const tier = metaOf("founder.model_class").choices.find((choice) => choice.value === modelClass)?.label ?? modelClass;
  const special = metaOf("founder.credential").special?.value;

  return (
    <section className="card settings-card" aria-labelledby="founder-title">
      <div className="settings-card-head">
        <h3 id="founder-title">{words.cardTitle}</h3>
        <p className="quiet">{words.intro}</p>
      </div>
      {data.error ? (
        <div className="stack">
          <ErrorNote error={data.error} />
          <div>
            <button type="button" className="button small" onClick={data.reload}>
              {settingsWords.common.retry}
            </button>
          </div>
        </div>
      ) : null}
      {data.loading && !data.data ? <Skeleton lines={4} block /> : null}
      {install && credentials ? (
        <>
          <div className={ready ? "note note-success" : "note note-warning"} role="status">
            <p className="note-title">
              {ready ? words.ready(credential, tier) : credential && credential !== special ? words.missingKey(credential) : words.notReady}
            </p>
            {ready && back ? (
              <div className="note-actions">
                <Link to={back} className="button primary">
                  {words.backToDraft}
                </Link>
              </div>
            ) : null}
          </div>
          {keys.length === 0 ? (
            <div className="empty compact">
              <span className="empty-icon" aria-hidden="true">
                <KeyRound size={20} />
              </span>
              <p className="empty-title">{words.noKeysTitle}</p>
              <p className="quiet">{words.noKeysBody}</p>
              <Link to="/settings/models" className="button primary empty-action">
                {words.goToKeys}
              </Link>
            </div>
          ) : (
            <FounderForm
              key={`${credential}-${modelClass}`}
              keys={keys}
              credential={credential}
              modelClass={modelClass}
              reason={words.reason}
              submitLabel={words.save}
              onSaved={(view) => {
                if (view) data.setData([view, credentials]);
              }}
            />
          )}
        </>
      ) : null}
    </section>
  );
}

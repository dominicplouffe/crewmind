/**
 * Install settings (GOV-1): limits and record keeping for every project, changed by an admin with
 * a reason. The Founder's two settings are in the Founder section instead.
 */
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { SettingsForm } from "./SettingsForm";

const ELSEWHERE = ["founder.credential", "founder.model_class"];

export function InstallSection(): JSX.Element {
  const words = settingsWords.install;
  const install = useLoad(() => get("/v1/settings/show_install"), []);
  return (
    <section className="card settings-card" aria-labelledby="install-title">
      <div className="settings-card-head">
        <h3 id="install-title">{words.cardTitle}</h3>
        <p className="quiet">{words.intro}</p>
      </div>
      {install.error ? (
        <div className="stack">
          <ErrorNote error={install.error} />
          <div>
            <button type="button" className="button small" onClick={install.reload}>
              {settingsWords.common.retry}
            </button>
          </div>
        </div>
      ) : null}
      {install.loading && !install.data ? <Skeleton lines={6} /> : null}
      {install.data ? (
        <SettingsForm
          label={words.title}
          view={install.data}
          grouped
          exclude={ELSEWHERE}
          needsReason
          onSave={async (changes, reason) => {
            install.setData(await post("/v1/settings/change_install", { changes, reason }));
          }}
        />
      ) : null}
    </section>
  );
}

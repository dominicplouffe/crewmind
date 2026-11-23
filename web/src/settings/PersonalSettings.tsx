/** A few of the person's own settings (scope person): saved at once, no reason needed. */
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { SettingsForm } from "./SettingsForm";

export function PersonalSettings({ only, label }: { only: string[]; label: string }): JSX.Element {
  const mine = useLoad(() => get("/v1/settings/show_mine"), []);
  if (mine.error && !mine.data) {
    return (
      <div className="stack">
        <ErrorNote error={mine.error} />
        <div>
          <button type="button" className="button small" onClick={mine.reload}>
            {settingsWords.common.retry}
          </button>
        </div>
      </div>
    );
  }
  if (!mine.data) return <Skeleton lines={only.length + 1} />;
  return (
    <SettingsForm
      label={label}
      view={mine.data}
      only={only}
      needsReason={false}
      onSave={async (changes) => {
        mine.setData(await post("/v1/settings/change_mine", { changes }));
      }}
    />
  );
}

/**
 * Which model key the Founder uses and at what quality (LLM-14, FND-2): the install settings
 * `founder.credential` and `founder.model_class`, chosen as cards and saved as one change.
 */
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { KeyRound } from "lucide-react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { metaOf } from "../lib/settingsMeta";
import { refreshSetupStatus } from "../onboarding/useSetupStatus";
import { settingsWords } from "../strings.settings";
import { ChoiceCard } from "./ChoiceCard";
import { useProviderLabels } from "./providers";

type Credential = Schemas["CredentialItem"];
type View = Schemas["SettingsView"];

interface Props {
  /** The usable model keys. */
  keys: Credential[];
  credential: string;
  modelClass: string;
  /** Kept in the install's history with the change. */
  reason: string;
  submitLabel: string;
  /** Called after saving, with the new install settings (or null when nothing changed). */
  onSaved(view: View | null): void;
  /** Placed before the submit button, such as Back. */
  before?: ReactNode;
}

export function FounderForm({ keys, credential, modelClass, reason, submitLabel, onSaved, before }: Props): JSX.Element {
  const words = settingsWords.founder;
  const id = useId();
  const labels = useProviderLabels();
  const tiers = metaOf("founder.model_class").choices.map((choice) => choice.value);
  const usable = keys.some((key) => key.name === credential) ? credential : (keys[0]?.name ?? "");
  const [chosenKey, setChosenKey] = useState(usable);
  const [tier, setTier] = useState(tiers.includes(modelClass) ? modelClass : (tiers[tiers.length - 1] ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const changes: Record<string, string> = {};
    if (chosenKey && chosenKey !== credential) changes["founder.credential"] = chosenKey;
    if (tier && tier !== modelClass) changes["founder.model_class"] = tier;
    if (Object.keys(changes).length === 0) {
      onSaved(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const view = await post("/v1/settings/change_install", { changes, reason });
      refreshSetupStatus();
      onSaved(view);
    } catch (reason_) {
      setError(reason_);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="founder-form" onSubmit={(event) => void submit(event)}>
      <fieldset className="choice-cards">
        <legend>{words.key}</legend>
        {keys.map((key) => (
          <ChoiceCard
            key={key.name}
            name={`${id}-key`}
            value={key.name}
            checked={chosenKey === key.name}
            onChange={() => setChosenKey(key.name)}
            title={key.name}
            help={labels(key.provider) === key.name ? undefined : labels(key.provider)}
            icon={<KeyRound size={16} />}
          />
        ))}
      </fieldset>
      <fieldset className="choice-cards tiers">
        <legend>{words.tier}</legend>
        <p className="quiet choice-cards-help">{words.tierHelp}</p>
        {tiers.map((value) => (
          <ChoiceCard
            key={value}
            name={`${id}-tier`}
            value={value}
            checked={tier === value}
            onChange={() => setTier(value)}
            title={words.tiers[value]?.label ?? value}
            help={words.tiers[value]?.help}
          />
        ))}
      </fieldset>
      <ErrorNote error={error} />
      <div className="form-actions">
        {before}
        <button type="submit" className="button primary" disabled={busy || !chosenKey}>
          {busy ? settingsWords.common.saving : submitLabel}
        </button>
      </div>
    </form>
  );
}

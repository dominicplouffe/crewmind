/** Change the name you are shown by (ACC-8). Used in Settings and in first-run setup. */
import { useState, type FormEvent } from "react";
import { post } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { settingsWords } from "../strings.settings";

export function NameForm({ compact = false }: { compact?: boolean }): JSX.Element | null {
  const words = settingsWords.profile;
  const { person, reload } = useAuth();
  const [name, setName] = useState(person?.name === words.seededName ? "" : (person?.name ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  if (!person) return null;
  const changed = name.trim() !== "" && name.trim() !== person.name;

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!changed) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await post("/v1/auth/set_name", { name: name.trim() });
      await reload();
      setSaved(true);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className={compact ? "name-form compact" : "name-form"} onSubmit={(event) => void submit(event)}>
      <label htmlFor="your-name">{words.nameLabel}</label>
      <div className="row">
        <input
          id="your-name"
          autoComplete="name"
          value={name}
          placeholder={words.namePlaceholder}
          aria-describedby="your-name-hint"
          onChange={(event) => {
            setName(event.target.value);
            setSaved(false);
          }}
        />
        <button type="submit" className="button" disabled={busy || !changed}>
          {busy ? settingsWords.common.saving : settingsWords.common.save}
        </button>
      </div>
      <p className="quiet" id="your-name-hint" role="status">
        {saved ? words.nameSaved : words.nameHint}
      </p>
      <ErrorNote error={error} />
    </form>
  );
}

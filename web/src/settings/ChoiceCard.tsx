/** A radio choice shown as a card: a title, a line of help and an optional icon. The whole card is the label. */
import type { ReactNode } from "react";

interface Props {
  name: string;
  value: string;
  checked: boolean;
  onChange(): void;
  title: string;
  help?: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export function ChoiceCard({ name, value, checked, onChange, title, help, icon, disabled = false }: Props): JSX.Element {
  return (
    <label className="choice-card">
      <input type="radio" name={name} value={value} checked={checked} disabled={disabled} onChange={onChange} />
      {icon ? (
        <span className="choice-card-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <span className="choice-card-text">
        <span className="choice-card-title">{title}</span>
        {help ? <span className="choice-card-help">{help}</span> : null}
      </span>
    </label>
  );
}

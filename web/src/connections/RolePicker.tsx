/** Choosing the roles of a project that may use a connection (CON-4): chips, plus "Every role". */
import { useId } from "react";
import type { Schemas } from "../api/client";
import { connectionWords as words } from "../strings.connections";

const ALL = "*";

interface Props {
  legend: string;
  help?: string;
  roles: Schemas["RoleOption"][];
  chosen: string[];
  onChange(roles: string[]): void;
}

export function RolePicker({ legend, help, roles, chosen, onChange }: Props): JSX.Element {
  const id = useId();
  const every = chosen.includes(ALL);
  const toggle = (slug: string): void => {
    if (slug === ALL) {
      onChange(every ? [] : [ALL]);
      return;
    }
    const without = chosen.filter((role) => role !== ALL && role !== slug);
    onChange(chosen.includes(slug) ? without : [...without, slug]);
  };
  return (
    <fieldset className="role-picker" aria-describedby={help ? `${id}-help` : undefined}>
      <legend>{legend}</legend>
      {help ? (
        <p className="quiet" id={`${id}-help`}>
          {help}
        </p>
      ) : null}
      <div className="chips">
        <label className={every ? "chip chip-on" : "chip"}>
          <input type="checkbox" checked={every} onChange={() => toggle(ALL)} />
          {words.project.allRoles}
        </label>
        {roles.map((role) => {
          const on = every || chosen.includes(role.slug);
          return (
            <label key={role.slug} className={on ? "chip chip-on" : "chip"}>
              <input type="checkbox" checked={on} disabled={every} onChange={() => toggle(role.slug)} />
              {role.name}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Who is signed in, the theme, and how agents talk to this person. */
import { Monitor, Moon, Sun } from "lucide-react";
import { useAuth } from "../auth";
import { useThemeContext } from "../components/ThemeButton";
import { settingsWords } from "../strings.settings";
import { Avatar } from "../ui/Avatar";
import { Pill } from "../ui/Status";
import { ChoiceCard } from "./ChoiceCard";
import { NameForm } from "./NameForm";
import { PersonalSettings } from "./PersonalSettings";

type Preference = "system" | "light" | "dark";
const THEMES: { value: Preference; icon: JSX.Element }[] = [
  { value: "system", icon: <Monitor size={18} aria-hidden="true" /> },
  { value: "light", icon: <Sun size={18} aria-hidden="true" /> },
  { value: "dark", icon: <Moon size={18} aria-hidden="true" /> },
];

export function ProfileSection(): JSX.Element {
  const words = settingsWords.profile;
  const { person } = useAuth();
  const { preference, setPreference } = useThemeContext();

  return (
    <>
      <section className="card settings-card" aria-labelledby="profile-title">
        <h3 id="profile-title" className="visually-hidden">
          {words.title}
        </h3>
        {person ? (
          <div className="profile">
            <Avatar name={person.name} kind="person" size="xl" />
            <div className="profile-text">
              <p className="profile-name">
                {person.name} <Pill tone={person.role === "admin" ? "accent" : "neutral"} dot={false}>{words.role[person.role] ?? person.role}</Pill>
              </p>
              <p className="quiet">{person.email}</p>
              <p className="quiet profile-note">{words.nameNote}</p>
            </div>
          </div>
        ) : null}
        <NameForm />
      </section>

      <section className="card settings-card" aria-labelledby="appearance-title">
        <div className="settings-card-head">
          <h3 id="appearance-title">{words.appearance}</h3>
          <p className="quiet">{words.appearanceHelp}</p>
        </div>
        <fieldset className="choice-cards theme-cards">
          <legend className="visually-hidden">{words.appearance}</legend>
          {THEMES.map(({ value, icon }) => (
            <ChoiceCard
              key={value}
              name="theme"
              value={value}
              checked={preference === value}
              onChange={() => setPreference(value)}
              title={words.theme[value]}
              help={words.themeHelp[value]}
              icon={icon}
            />
          ))}
        </fieldset>
      </section>

      <section className="card settings-card" aria-labelledby="conversation-title">
        <div className="settings-card-head">
          <h3 id="conversation-title">{words.conversation}</h3>
        </div>
        <PersonalSettings label={words.conversation} only={["chat.brevity", "grill.pace", "person.timezone", "token.default_expiry"]} />
      </section>
    </>
  );
}

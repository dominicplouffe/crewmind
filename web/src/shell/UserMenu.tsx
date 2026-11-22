/** The person's menu: theme, alerts, settings and sign out. The theme toggle lives here now. */
import { Bell, BellOff, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useThemeContext } from "../components/ThemeButton";
import { shell } from "../strings.shell";
import { Avatar } from "../ui/Avatar";
import { Menu, type MenuItem } from "../ui/Menu";
import { useAlerts } from "./useAlerts";

export function UserMenu({ compact = false, placement = "above" }: { compact?: boolean; placement?: "above" | "below" }): JSX.Element | null {
  const { person, signOut } = useAuth();
  const navigate = useNavigate();
  const { preference, setPreference } = useThemeContext();
  const alerts = useAlerts();
  if (!person) return null;
  const words = shell.user;
  const items: (MenuItem | "separator")[] = [
    { key: "system", label: words.system, icon: <Monitor size={16} />, checked: preference === "system", run: () => setPreference("system") },
    { key: "light", label: words.light, icon: <Sun size={16} />, checked: preference === "light", run: () => setPreference("light") },
    { key: "dark", label: words.dark, icon: <Moon size={16} />, checked: preference === "dark", run: () => setPreference("dark") },
    "separator",
  ];
  if (alerts.state === "on" || alerts.state === "off") {
    items.push({
      key: "alerts",
      label: alerts.state === "on" ? words.alertsOff : words.alertsOn,
      icon: alerts.state === "on" ? <BellOff size={16} /> : <Bell size={16} />,
      run: () => void alerts.toggle(),
    });
  }
  items.push(
    { key: "settings", label: words.settings, icon: <Settings size={16} />, run: () => navigate("/settings") },
    "separator",
    { key: "signout", label: words.signOut, icon: <LogOut size={16} />, danger: true, run: () => void signOut() },
  );
  return (
    <Menu
      label={words.menu(person.name)}
      className={compact ? "button ghost icon-only user-button compact" : "button ghost user-button"}
      align={compact ? "end" : "start"}
      placement={placement}
      testId="user-menu"
      labelButton={false}
      button={
        <>
          <Avatar name={person.name} kind="person" size="sm" />
          {compact ? <span className="visually-hidden">{words.menu(person.name)}</span> : null}
          {compact ? null : (
            <span className="user-text">
              <span className="user-name">{person.name}</span>
              <span className="user-role">{person.role === "admin" ? words.admin : words.member}</span>
              <span className="visually-hidden">{words.menuSuffix}</span>
            </span>
          )}
        </>
      }
      items={items}
    />
  );
}

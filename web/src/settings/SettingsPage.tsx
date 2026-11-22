/**
 * Settings, at `/settings/:section?`. A sub-nav on the left on a desktop; on a phone the list of
 * sections comes first and each opens on its own, with a way back. Sections an admin manages are
 * hidden from members, with a plain note saying so.
 */
import { useEffect, useRef, type ComponentType } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { Bell, ChevronLeft, ChevronRight, KeyRound, Settings2, Sparkles, UserRound, Users } from "lucide-react";
import { useAuth } from "../auth";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { FounderSection } from "./FounderSection";
import { InstallSection } from "./InstallSection";
import { ModelsSection } from "./ModelsSection";
import { NotificationsSection } from "./NotificationsSection";
import { PeopleSection } from "./PeopleSection";
import type { SectionId } from "./paths";
import { ProfileSection } from "./ProfileSection";


interface Section {
  id: SectionId;
  icon: JSX.Element;
  adminOnly: boolean;
  body: ComponentType;
}

const SECTIONS: Section[] = [
  { id: "profile", icon: <UserRound size={18} aria-hidden="true" />, adminOnly: false, body: ProfileSection },
  { id: "notifications", icon: <Bell size={18} aria-hidden="true" />, adminOnly: false, body: NotificationsSection },
  { id: "models", icon: <KeyRound size={18} aria-hidden="true" />, adminOnly: false, body: ModelsSection },
  { id: "founder", icon: <Sparkles size={18} aria-hidden="true" />, adminOnly: true, body: FounderSection },
  { id: "people", icon: <Users size={18} aria-hidden="true" />, adminOnly: true, body: PeopleSection },
  { id: "install", icon: <Settings2 size={18} aria-hidden="true" />, adminOnly: true, body: InstallSection },
];

export function SettingsPage(): JSX.Element {
  const words = settingsWords.page;
  const { section: wanted } = useParams();
  const { person } = useAuth();
  const isAdmin = person?.role === "admin";
  const visible = SECTIONS.filter((section) => isAdmin || !section.adminOnly);
  const known = SECTIONS.find((section) => section.id === wanted);
  // With no section in the address, a desktop shows the first one; a phone shows the list.
  const current = known ?? (wanted ? null : (SECTIONS[0] ?? null));
  const allowed = current !== null && (isAdmin || !current.adminOnly);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = words.documentTitle;
  }, [words.documentTitle]);

  // Moving between sections puts focus on the new section's heading (not on first load).
  const shown = useRef(wanted);
  useEffect(() => {
    if (shown.current === wanted) return;
    shown.current = wanted;
    heading.current?.focus();
  }, [wanted]);

  const Body = current?.body;
  return (
    <div className={wanted ? "settings-page has-section" : "settings-page at-index"}>
      <header className="page-head settings-head">
        <div>
          <h1>{words.title}</h1>
          <p>{words.intro}</p>
        </div>
      </header>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label={words.nav}>
          <ul className="plain">
            {visible.map((section) => (
              <li key={section.id}>
                <NavLink
                  to={`/settings/${section.id}`}
                  className={({ isActive }) => (isActive || (!wanted && section === SECTIONS[0]) ? "settings-nav-link active" : "settings-nav-link")}
                  aria-current={wanted && section === current ? "page" : undefined}
                >
                  <span className="settings-nav-icon">{section.icon}</span>
                  <span className="settings-nav-text">
                    <span className="settings-nav-label">{settingsWords.sections[section.id].label}</span>
                    <span className="settings-nav-help">{settingsWords.sections[section.id].help}</span>
                  </span>
                  <ChevronRight size={16} className="settings-nav-chevron" aria-hidden="true" />
                </NavLink>
              </li>
            ))}
          </ul>
          {person && !isAdmin ? <p className="quiet settings-nav-note">{words.adminOnly}</p> : null}
        </nav>
        <div className="settings-content">
          <Link to="/settings" className="settings-back button ghost">
            <ChevronLeft size={16} aria-hidden="true" />
            {words.backToList}
          </Link>
          {current ? (
            <h2 className="settings-section-title" tabIndex={-1} ref={heading}>
              {settingsWords.sections[current.id].label}
            </h2>
          ) : null}
          {person === undefined ? (
            <Skeleton lines={5} block />
          ) : current === null ? (
            <div className="note note-warning">
              <p className="note-title">{words.notFound}</p>
            </div>
          ) : !allowed ? (
            <div className="note">
              <p className="note-title">{words.adminOnlyTitle}</p>
              <p className="note-hint">{words.adminOnlyBody}</p>
            </div>
          ) : Body ? (
            <div className="settings-section" key={current.id}>
              <Body />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

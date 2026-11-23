/**
 * Routes (docs/design/ia-map.md). Two primary places, Home and Projects, plus Settings, inside the
 * app shell. Sign-in, accepting a link and first-run setup are full-screen, outside the shell.
 */
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { ThemeProvider } from "./components/ThemeButton";
import { DraftPage } from "./founder/DraftPage";
import { isApprovalLink } from "./lib/oauth";
import { NeedsYouProvider } from "./needs/NeedsYou";
import { AcceptLink } from "./pages/AcceptLink";
import { Home } from "./pages/Home";
import { OAuthApprove } from "./pages/OAuthApprove";
import { Projects } from "./pages/Projects";
import { SignIn } from "./pages/SignIn";
import { AppShell } from "./shell/AppShell";
import { PaletteProvider } from "./shell/palette";
import { ProjectsProvider } from "./shell/projects";
import { LogoMark } from "./ui/Logo";
import { Skeleton } from "./ui/Skeleton";

const Project = lazy(() => import("./pages/Project").then((module) => ({ default: module.Project })));
const SettingsPage = lazy(() => import("./settings/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const Welcome = lazy(() => import("./onboarding/Welcome").then((module) => ({ default: module.Welcome })));

function Splash(): JSX.Element {
  return (
    <main className="center-page splash">
      <LogoMark size={40} />
      <Skeleton lines={0} />
    </main>
  );
}

function SignedIn({ children }: { children: JSX.Element }): JSX.Element {
  const { person } = useAuth();
  const location = useLocation();
  if (person === undefined) return <Splash />;
  if (person === null) {
    // The whole address is kept, so a link that carries its request after "#" still works after sign-in.
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/signin" replace state={{ from }} />;
  }
  return children;
}

/** The shell around every signed-in page. Inside a project the phone's tab bar steps aside. */
function Shell(): JSX.Element {
  return (
    <SignedIn>
      <ProjectsProvider>
        <PaletteProvider>
          <AppShell>
            <Suspense fallback={<Skeleton lines={4} block />}>
              <Outlet />
            </Suspense>
          </AppShell>
        </PaletteProvider>
      </ProjectsProvider>
    </SignedIn>
  );
}

/** The start page: Home, or the approval page when the server sent the browser here to approve a client. */
function Start(): JSX.Element {
  const { hash } = useLocation();
  return isApprovalLink(hash) ? <OAuthApprove hash={hash} /> : <Home />;
}

/** Remounts the project page when the project changes, so nothing from the last one lingers. */
function ProjectRoute(): JSX.Element {
  const { projectId = "" } = useParams();
  return <Project key={projectId} />;
}

export function App(): JSX.Element {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <NeedsYouProvider>
            <Routes>
              <Route path="/signin" element={<SignIn />} />
              <Route path="/accept/:token" element={<AcceptLink />} />
              <Route
                path="/welcome"
                element={
                  <SignedIn>
                    <Suspense fallback={<Splash />}>
                      <Welcome />
                    </Suspense>
                  </SignedIn>
                }
              />
              <Route element={<Shell />}>
                <Route path="/" element={<Start />} />
                <Route path="/desk" element={<Navigate to="/" replace />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/projects/:projectId" element={<ProjectRoute />} />
                <Route path="/projects/:projectId/:tab" element={<ProjectRoute />} />
                <Route path="/draft" element={<DraftPage />} />
                <Route path="/draft/:draftingId" element={<DraftPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/:section" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </NeedsYouProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

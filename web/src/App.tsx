/** Routes: sign in, accept a link, the project list, the Desk, drafting a project, a project, approving an AI client. */
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Loading } from "./components/common";
import { ThemeProvider } from "./components/ThemeButton";
import { DeskPage } from "./desk/DeskPage";
import { DraftPage } from "./founder/DraftPage";
import { isApprovalLink } from "./lib/oauth";
import { AcceptLink } from "./pages/AcceptLink";
import { OAuthApprove } from "./pages/OAuthApprove";
import { Projects } from "./pages/Projects";
import { SignIn } from "./pages/SignIn";

const Project = lazy(() => import("./pages/Project").then((module) => ({ default: module.Project })));

function SignedIn({ children }: { children: JSX.Element }): JSX.Element {
  const { person } = useAuth();
  const location = useLocation();
  if (person === undefined) {
    return (
      <main className="center-page">
        <Loading />
      </main>
    );
  }
  if (person === null) {
    // The whole address is kept, so a link that carries its request after "#" still works after sign-in.
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/signin" replace state={{ from }} />;
  }
  return children;
}

/** The start page: the project list, or the approval page when the server sent the browser here to approve a client. */
function Home(): JSX.Element {
  const { hash } = useLocation();
  return isApprovalLink(hash) ? <OAuthApprove hash={hash} /> : <Projects />;
}

export function App(): JSX.Element {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/signin" element={<SignIn />} />
            <Route path="/accept/:token" element={<AcceptLink />} />
            <Route
              path="/"
              element={
                <SignedIn>
                  <Home />
                </SignedIn>
              }
            />
            <Route
              path="/desk"
              element={
                <SignedIn>
                  <DeskPage />
                </SignedIn>
              }
            />
            {["/draft", "/draft/:draftingId"].map((path) => (
              <Route
                key={path}
                path={path}
                element={
                  <SignedIn>
                    <DraftPage />
                  </SignedIn>
                }
              />
            ))}
            <Route
              path="/projects/:projectId"
              element={
                <SignedIn>
                  <Suspense fallback={<Loading />}>
                    <Project />
                  </Suspense>
                </SignedIn>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

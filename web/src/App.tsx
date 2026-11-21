/** Routes: sign in, accept a link, the project list, a project. */
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Loading } from "./components/common";
import { ThemeProvider } from "./components/ThemeButton";
import { AcceptLink } from "./pages/AcceptLink";
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
  if (person === null) return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  return children;
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
                  <Projects />
                </SignedIn>
              }
            />
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

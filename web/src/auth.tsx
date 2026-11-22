/** Who is signed in. Asks the server once, and again after sign-in or sign-out. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, get, post, setSignedOutHandler, type Schemas } from "./api/client";

type Person = Schemas["WhoAmI"];

interface AuthValue {
  /** `undefined` while loading, `null` when signed out. */
  person: Person | null | undefined;
  reload(): Promise<void>;
  signOut(): Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [person, setPerson] = useState<Person | null | undefined>(undefined);

  const reload = useCallback(async () => {
    try {
      setPerson(await get("/v1/auth/whoami"));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setPerson(null);
      else setPerson(null);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await post("/v1/auth/logout", {});
    } finally {
      setPerson(null);
    }
  }, []);

  useEffect(() => {
    setSignedOutHandler(() => setPerson(null));
    void reload();
    return () => setSignedOutHandler(null);
  }, [reload]);

  const value = useMemo(() => ({ person, reload, signOut }), [person, reload, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth needs an AuthProvider");
  return value;
}

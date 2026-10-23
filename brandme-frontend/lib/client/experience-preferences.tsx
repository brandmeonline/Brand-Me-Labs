"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from "react";
export type ThemeMode = "system" | "light" | "dark";
type Preferences = {
  theme: ThemeMode;
  motion: "system" | "reduce";
  simpleView: boolean;
  highContrast: boolean;
};
const defaults: Preferences = {
  theme: "system",
  motion: "system",
  simpleView: false,
  highContrast: false,
};
const storageKey = "brandme:experience:v1";
function decode(value: string | null): Preferences {
  try {
    const data = JSON.parse(value || "{}");
    return {
      theme: ["system", "light", "dark"].includes(data?.theme)
        ? data.theme
        : "system",
      motion: data?.motion === "reduce" ? "reduce" : "system",
      simpleView: data?.simpleView === true,
      highContrast: data?.highContrast === true,
    };
  } catch {
    return defaults;
  }
}
const ExperienceContext = createContext<{
  preferences: Preferences;
  reducedMotion: boolean;
  simpleView: boolean;
  storageAvailable: boolean;
  ready: boolean;
  update: (patch: Partial<Preferences>) => void;
} | null>(null);
export function ExperiencePreferencesProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [preferences, setPreferences] = useState<Preferences>(defaults);
  const current = useRef<Preferences>(defaults);
  const [osReduced, setOsReduced] = useState(true);
  const [osDark, setOsDark] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  useEffect(() => {
    try {
      current.current = decode(localStorage.getItem(storageKey));
      setPreferences(current.current);
    } catch {
      setStorageAvailable(false);
    }
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const darkQuery = matchMedia("(prefers-color-scheme: dark)");
    const syncMotion = () => setOsReduced(query.matches);
    const syncTheme = () => setOsDark(darkQuery.matches);
    const syncStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) {
        current.current = decode(event.newValue);
        setPreferences(current.current);
      }
    };
    syncMotion();
    syncTheme();
    setInitialized(true);
    query.addEventListener("change", syncMotion);
    darkQuery.addEventListener("change", syncTheme);
    window.addEventListener("storage", syncStorage);
    return () => {
      query.removeEventListener("change", syncMotion);
      darkQuery.removeEventListener("change", syncTheme);
      window.removeEventListener("storage", syncStorage);
    };
  }, []);
  useEffect(() => {
    if (!initialized) return;
    document.documentElement.dataset.bmPreferencesReady = "true";
    document.documentElement.dataset.bmTheme =
      preferences.theme === "system"
        ? osDark
          ? "dark"
          : "light"
        : preferences.theme;
    document.documentElement.dataset.bmMotion = preferences.motion;
    document.documentElement.dataset.theme =
      document.documentElement.dataset.bmTheme;
    document.documentElement.dataset.motion =
      preferences.motion === "reduce" || osReduced ? "reduced" : "system";
    document.documentElement.dataset.bmContrast = preferences.highContrast
      ? "high"
      : "standard";
    document.documentElement.dataset.bmSimpleView = String(
      preferences.simpleView,
    );
  }, [preferences, initialized, osDark, osReduced]);
  function update(patch: Partial<Preferences>) {
    if (!initialized) return;
    const next = { ...current.current, ...patch };
    current.current = next;
    setPreferences(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      setStorageAvailable(true);
    } catch {
      setStorageAvailable(false);
    }
  }
  return (
    <ExperienceContext.Provider
      value={{
        preferences,
        reducedMotion: osReduced || preferences.motion === "reduce",
        simpleView: preferences.simpleView,
        storageAvailable,
        ready: initialized,
        update,
      }}
    >
      {children}
    </ExperienceContext.Provider>
  );
}
export function useExperiencePreferences() {
  const context = useContext(ExperienceContext);
  if (!context) throw new Error("ExperiencePreferencesProvider is required");
  return context;
}

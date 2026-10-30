"use client";
import { useId } from "react";
import { Switch } from "@/components/ui/field";
import {
  useExperiencePreferences,
  type ThemeMode,
} from "@/lib/client/experience-preferences";
import { useFriendResponseHaptics } from "@/lib/client/haptic-preferences";
export function ExperienceSettings() {
  const id = useId();
  const { preferences, update, storageAvailable, reducedMotion, ready } =
    useExperiencePreferences();
  const haptics = useFriendResponseHaptics();
  return (
    <div className="bm-experience-settings">
      <fieldset className="bm-choice-fieldset" disabled={!ready}>
        <legend>Appearance</legend>
        <div className="bm-segmented">
          {(["system", "light", "dark"] as ThemeMode[]).map((theme) => (
            <label key={theme}>
              <input
                type="radio"
                name={`${id}-theme`}
                value={theme}
                checked={preferences.theme === theme}
                onChange={() => update({ theme })}
              />
              <span>
                {theme === "system"
                  ? "Automatic"
                  : theme === "light"
                    ? "Light"
                    : "Dark"}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Switch
        label="Reduce motion"
        disabled={!ready}
        description="Keep changes clear. Skip camera flights and parallax."
        checked={preferences.motion === "reduce"}
        onCheckedChange={(checked) =>
          update({ motion: checked ? "reduce" : "system" })
        }
      />
      <p className="bm-support">
        {reducedMotion
          ? "Reduced motion is active."
          : "Your device’s motion preference is also respected."}
      </p>
      <Switch
        label="Friend response heartbeat"
        disabled={!haptics.ready}
        description="A gentle vibration when a friend answers your request. When supported; paused with reduced motion."
        checked={haptics.enabled}
        onCheckedChange={haptics.setEnabled}
      />
      {!haptics.storageAvailable && (
        <p className="bm-support" role="status">
          Your heartbeat preference could not be saved on this device.
        </p>
      )}
      <Switch
        label="Prefer Simple View"
        disabled={!ready}
        description="Ask supported wardrobe views to use a list instead of 3D."
        checked={preferences.simpleView}
        onCheckedChange={(checked) => update({ simpleView: checked })}
      />
      <Switch
        label="Stronger contrast"
        disabled={!ready}
        description="Give secondary text and boundaries more definition."
        checked={preferences.highContrast}
        onCheckedChange={(checked) => update({ highContrast: checked })}
      />
      <p className="bm-storage-note" role="status">
        {storageAvailable
          ? "Display preferences are saved on this device."
          : "Your browser cannot save preferences. These changes last for this visit."}
      </p>
    </div>
  );
}

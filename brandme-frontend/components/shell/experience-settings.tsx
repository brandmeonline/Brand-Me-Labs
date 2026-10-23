'use client'
import { useId } from 'react'
import { Switch } from '@/components/ui/field'
import {
  useExperiencePreferences,
  type ThemeMode,
} from '@/lib/client/experience-preferences'
export function ExperienceSettings() {
  const id = useId()
  const { preferences, update, storageAvailable, reducedMotion } =
    useExperiencePreferences()
  return (
    <div className="bm-experience-settings">
      <fieldset className="bm-choice-fieldset">
        <legend>Appearance</legend>
        <div className="bm-segmented">
          {(['system', 'light', 'dark'] as ThemeMode[]).map((theme) => (
            <label key={theme}>
              <input
                type="radio"
                name={`${id}-theme`}
                value={theme}
                checked={preferences.theme === theme}
                onChange={() => update({ theme })}
              />
              <span>
                {theme === 'system'
                  ? 'Automatic'
                  : theme === 'light'
                    ? 'Light'
                    : 'Dark'}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Switch
        label="Reduce motion"
        description="Keep changes clear. Skip camera flights and parallax."
        checked={preferences.motion === 'reduce'}
        onCheckedChange={(checked) =>
          update({ motion: checked ? 'reduce' : 'system' })
        }
      />
      <p className="bm-support">
        {reducedMotion
          ? 'Reduced motion is active.'
          : 'Your device’s motion preference is also respected.'}
      </p>
      <Switch
        label="Prefer Simple View"
        description="Ask supported wardrobe views to use a list instead of 3D."
        checked={preferences.simpleView}
        onCheckedChange={(checked) => update({ simpleView: checked })}
      />
      <Switch
        label="Stronger contrast"
        description="Give secondary text and boundaries more definition."
        checked={preferences.highContrast}
        onCheckedChange={(checked) => update({ highContrast: checked })}
      />
      <p className="bm-storage-note" role="status">
        {storageAvailable
          ? 'Display preferences are saved on this device.'
          : 'Your browser cannot save preferences. These changes last for this visit.'}
      </p>
    </div>
  )
}

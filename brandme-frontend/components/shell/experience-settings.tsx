'use client'
import { useId } from 'react'
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
      <label className="bm-setting-row">
        <span>
          <strong>Reduce motion</strong>
          <span className="bm-support">
            Keep changes clear. Skip camera flights and parallax.
          </span>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={preferences.motion === 'reduce'}
          onChange={(e) =>
            update({ motion: e.target.checked ? 'reduce' : 'system' })
          }
        />
      </label>
      <p className="bm-support">
        {reducedMotion
          ? 'Reduced motion is active.'
          : 'Your device’s motion preference is also respected.'}
      </p>
      <label className="bm-setting-row">
        <span>
          <strong>Prefer Simple View</strong>
          <span className="bm-support">
            Ask supported wardrobe views to use a list instead of 3D.
          </span>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={preferences.simpleView}
          onChange={(e) => update({ simpleView: e.target.checked })}
        />
      </label>
      <label className="bm-setting-row">
        <span>
          <strong>Stronger contrast</strong>
          <span className="bm-support">
            Give secondary text and boundaries more definition.
          </span>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={preferences.highContrast}
          onChange={(e) => update({ highContrast: e.target.checked })}
        />
      </label>
      <p className="bm-storage-note" role="status">
        {storageAvailable
          ? 'Display preferences are saved on this device.'
          : 'Your browser cannot save preferences. These changes last for this visit.'}
      </p>
    </div>
  )
}

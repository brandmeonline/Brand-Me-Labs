'use client'

import { useEffect, useId, useState } from 'react'

/** A draft control only. Confirmed persistence and declared/inferred records belong to the domain. */
export function Slider({
  label,
  leftLabel,
  rightLabel,
  value,
  onValueChange,
  disabled = false,
}: {
  label: string
  leftLabel: string
  rightLabel: string
  value: number | null
  onValueChange: (value: number | null) => void
  disabled?: boolean
}) {
  const id = useId()
  const [numericDraft, setNumericDraft] = useState(
    value === null ? '' : String(value),
  )
  useEffect(() => setNumericDraft(value === null ? '' : String(value)), [value])
  const invalid =
    numericDraft !== '' &&
    (!/^(0|[1-9][0-9]*)$/.test(numericDraft) || Number(numericDraft) > 100)
  const current = value === null ? 'Not set' : `${value} of 100`
  function change(next: number) {
    const bounded = Math.max(0, Math.min(100, Math.round(next)))
    setNumericDraft(String(bounded))
    onValueChange(bounded)
  }
  return (
    <fieldset className="bm-slider" disabled={disabled}>
      <legend id={`${id}-label`}>{label}</legend>
      <p id={`${id}-help`} className="bm-support">
        {leftLabel} to {rightLabel}. {current}.
        {value === null
          ? ' The centered handle is a starting point, not a saved preference.'
          : ''}
      </p>
      <div className="bm-slider-endpoints" aria-hidden="true">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={value ?? 50}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-help`}
        aria-valuetext={
          value === null
            ? 'Not set; use arrows or enter a number to choose'
            : `${value} of 100, ${leftLabel} to ${rightLabel}`
        }
        onChange={(event) => change(event.target.valueAsNumber)}
        onKeyDown={(event) => {
          const steps: Record<string, number> = {
            ArrowRight: 5,
            ArrowUp: 5,
            ArrowLeft: -5,
            ArrowDown: -5,
            PageUp: 10,
            PageDown: -10,
          }
          const delta = steps[event.key]
          if (
            delta !== undefined ||
            event.key === 'Home' ||
            event.key === 'End'
          ) {
            event.preventDefault()
            change(
              event.key === 'Home'
                ? 0
                : event.key === 'End'
                  ? 100
                  : (value ?? 50) + (delta ?? 0),
            )
          }
        }}
      />
      <div className="bm-slider-entry">
        <label htmlFor={`${id}-number`}>{label} value</label>
        <input
          id={`${id}-number`}
          className="bm-input"
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          step={1}
          value={numericDraft}
          placeholder="Not set"
          aria-invalid={invalid || undefined}
          aria-describedby={`${id}-help${invalid ? ` ${id}-error` : ''}`}
          onChange={(event) => {
            const next = event.target.value
            setNumericDraft(next)
            if (next === '') onValueChange(null)
            else if (/^(0|[1-9][0-9]*)$/.test(next) && Number(next) <= 100)
              onValueChange(Number(next))
          }}
        />
        <button
          type="button"
          className="bm-text-link"
          onClick={() => {
            setNumericDraft('')
            onValueChange(null)
          }}
        >
          Clear {label.toLowerCase()}
        </button>
      </div>
      {invalid && (
        <p id={`${id}-error`} className="bm-field-error">
          Enter a whole number from 0 to 100. This value has not been applied.
        </p>
      )}
    </fieldset>
  )
}

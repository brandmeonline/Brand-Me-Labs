'use client'

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type ReactNode,
} from 'react'

type FieldInfo = { label: string; description?: string; error?: string }

function Field({
  id,
  label,
  description,
  error,
  children,
}: FieldInfo & { id: string; children: ReactNode }) {
  return (
    <div className="bm-field">
      <label htmlFor={id}>{label}</label>
      {description && (
        <p id={`${id}-help`} className="bm-support">
          {description}
        </p>
      )}
      {children}
      {error && (
        <p id={`${id}-error`} className="bm-field-error">
          {error}
        </p>
      )}
    </div>
  )
}
function describedBy(
  id: string,
  description?: string,
  error?: string,
  additional?: string,
) {
  return (
    [description && `${id}-help`, error && `${id}-error`, additional]
      .filter(Boolean)
      .join(' ') || undefined
  )
}

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & FieldInfo
>(function Input(
  { id: suppliedId, label, description, error, className = '', ...props },
  ref,
) {
  const generatedId = useId()
  const id = suppliedId || generatedId
  return (
    <Field id={id} label={label} description={description} error={error}>
      <input
        {...props}
        ref={ref}
        id={id}
        className={`bm-input ${className}`}
        aria-invalid={error ? true : props['aria-invalid']}
        aria-describedby={describedBy(
          id,
          description,
          error,
          props['aria-describedby'],
        )}
      />
    </Field>
  )
})

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & FieldInfo
>(function Select(
  {
    id: suppliedId,
    label,
    description,
    error,
    className = '',
    children,
    ...props
  },
  ref,
) {
  const generatedId = useId()
  const id = suppliedId || generatedId
  return (
    <Field id={id} label={label} description={description} error={error}>
      <select
        {...props}
        ref={ref}
        id={id}
        className={`bm-input ${className}`}
        aria-invalid={error ? true : props['aria-invalid']}
        aria-describedby={describedBy(
          id,
          description,
          error,
          props['aria-describedby'],
        )}
      >
        {children}
      </select>
    </Field>
  )
})

export function Switch({
  label,
  description,
  checked,
  onCheckedChange,
  disabled = false,
}: {
  label: string
  description?: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
}) {
  const id = useId()
  return (
    <label className="bm-setting-row" htmlFor={id}>
      <span>
        <strong id={`${id}-label`}>{label}</strong>
        {description && (
          <span id={`${id}-help`} className="bm-support">
            {description}
          </span>
        )}
      </span>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-labelledby={`${id}-label`}
        aria-describedby={description ? `${id}-help` : undefined}
        onChange={(event) => onCheckedChange(event.target.checked)}
      />
    </label>
  )
}

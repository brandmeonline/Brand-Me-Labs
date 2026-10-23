'use client'

import { useId, useRef, type ReactNode } from 'react'

export type TabItem = {
  id: string
  label: string
  content: ReactNode
  disabled?: boolean
}

/** Automatic keyboard activation for immediately available panels; keep network loading inside each panel. */
export function Tabs({
  label,
  items,
  value,
  onValueChange,
}: {
  label: string
  items: readonly TabItem[]
  value: string
  onValueChange: (value: string) => void
}) {
  const id = useId()
  const refs = useRef(new Map<string, HTMLButtonElement>())
  const enabled = items.filter((item) => !item.disabled)
  const selected = enabled.some((item) => item.id === value)
    ? value
    : enabled[0]?.id
  return (
    <div className="bm-tabs">
      <div role="tablist" aria-label={label} className="bm-tab-list">
        {items.map((item, index) => (
          <button
            key={item.id}
            ref={(node) => {
              if (node) refs.current.set(item.id, node)
              else refs.current.delete(item.id)
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${index}`}
            aria-controls={`${id}-panel-${index}`}
            aria-selected={selected === item.id}
            tabIndex={selected === item.id ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onValueChange(item.id)}
            onKeyDown={(event) => {
              const current = enabled.findIndex((entry) => entry.id === item.id)
              const next =
                event.key === 'Home'
                  ? 0
                  : event.key === 'End'
                    ? enabled.length - 1
                    : event.key === 'ArrowRight'
                      ? (current + 1) % enabled.length
                      : event.key === 'ArrowLeft'
                        ? (current - 1 + enabled.length) % enabled.length
                        : -1
              if (next < 0) return
              event.preventDefault()
              onValueChange(enabled[next].id)
              refs.current.get(enabled[next].id)?.focus()
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map((item, index) => (
        <div
          key={item.id}
          id={`${id}-panel-${index}`}
          role="tabpanel"
          aria-labelledby={`${id}-tab-${index}`}
          tabIndex={0}
          hidden={selected !== item.id}
          className="bm-tab-panel"
        >
          {item.content}
        </div>
      ))}
    </div>
  )
}

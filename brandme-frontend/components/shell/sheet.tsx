'use client'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
export function Sheet({
  title,
  description,
  trigger,
  children,
  open,
  onOpenChange,
  onCloseAutoFocus,
}: {
  title: string
  description: string
  trigger: ReactNode
  children: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onCloseAutoFocus?: (event: Event) => void
}) {
  const [snap, setSnap] = useState('full')
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="bm-sheet-overlay" />
        <Dialog.Content
          className="bm-sheet"
          data-snap={snap}
          onCloseAutoFocus={onCloseAutoFocus}
        >
          <div className="bm-sheet-heading">
            <Dialog.Title className="bm-section-title">{title}</Dialog.Title>
            <Dialog.Close
              className="bm-icon-button"
              aria-label={`Close ${title}`}
            >
              <X aria-hidden="true" size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="bm-support bm-sheet-description">
            {description}
          </Dialog.Description>
          <div
            className="bm-sheet-snaps"
            role="group"
            aria-label="Panel height"
          >
            {['compact', 'balanced', 'full'].map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={snap === value}
                onClick={() => setSnap(value)}
              >
                {value === 'compact'
                  ? 'Compact'
                  : value === 'balanced'
                    ? 'Medium'
                    : 'Full height'}
              </button>
            ))}
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

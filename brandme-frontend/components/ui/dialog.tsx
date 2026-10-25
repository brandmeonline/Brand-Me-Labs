'use client'

import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode, RefObject } from 'react'

export { Sheet as Drawer } from '../shell/sheet'

export function Dialog({
  title,
  description,
  trigger,
  children,
  open,
  onOpenChange,
  returnFocus,
}: {
  title: string
  description: string
  trigger?: ReactNode
  children: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  returnFocus?: RefObject<HTMLElement | null>
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="bm-sheet-overlay" />
        <RadixDialog.Content className="bm-dialog" onCloseAutoFocus={event => {
          if (returnFocus?.current?.isConnected) { event.preventDefault(); returnFocus.current.focus() }
        }}>
          <div className="bm-sheet-heading">
            <RadixDialog.Title className="bm-section-title">
              {title}
            </RadixDialog.Title>
            <RadixDialog.Close
              className="bm-icon-button"
              aria-label={`Close ${title}`}
            >
              <X size={20} aria-hidden="true" />
            </RadixDialog.Close>
          </div>
          <RadixDialog.Description className="bm-support bm-sheet-description">
            {description}
          </RadixDialog.Description>
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}

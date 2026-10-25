'use client'

import Link from 'next/link'
import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ComponentPropsWithoutRef,
} from 'react'

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary'
  pending?: boolean
  pendingLabel?: string
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = 'primary',
      pending = false,
      pendingLabel = 'Working…',
      disabled,
      type = 'button',
      className = '',
      children,
      ...props
    },
    ref,
  ) {
    return (
      <button
        {...props}
        ref={ref}
        type={type}
        disabled={disabled || pending}
        aria-busy={pending || undefined}
        className={`bm-button ${variant === 'secondary' ? 'bm-button-secondary' : ''} ${className}`}
      >
        {pending ? pendingLabel : children}
      </button>
    )
  },
)

/** Navigation remains a link; it never inherits button/pending semantics. */
export function ActionLink({
  className = '',
  ...props
}: ComponentPropsWithoutRef<typeof Link>) {
  return (
    <Link {...props} className={`bm-button bm-button-secondary ${className}`} />
  )
}

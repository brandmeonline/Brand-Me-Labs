export type Money = { amount_minor: string; currency: string }

export function currencyDigits(currency: string): number {
  if (!/^[A-Z]{3}$/.test(currency) || typeof Intl.supportedValuesOf !== 'function' ||
      !Intl.supportedValuesOf('currency').includes(currency) || currency === 'XXX' || currency === 'XTS')
    throw new Error('Choose a supported three-letter currency.')
  const digits = new Intl.NumberFormat('en-US', { style: 'currency', currency }).resolvedOptions().maximumFractionDigits
  if (digits === undefined) throw new Error('Currency exponent unavailable')
  return digits
}

/** Decimal text to integer text; never converts a quote or budget through floating point. */
export function parseMoneyInput(value: string, currency: string): string | null {
  const digits = currencyDigits(currency)
  if (value.trim() === '') return null
  const match = /^(\d+)(?:\.(\d*))?$/.exec(value.trim())
  if (!match || (match[2]?.length ?? 0) > digits || (digits === 0 && match[2] !== undefined))
    throw new Error(`Enter an amount with at most ${digits} decimal places.`)
  const minor = `${match[1]}${(match[2] ?? '').padEnd(digits, '0')}`.replace(/^0+(?=\d)/, '')
  if (minor.length > 18) throw new Error('This amount is too large.')
  return minor
}

export function moneyInputValue(amount: string | null, currency: string): string {
  if (amount === null) return ''
  const digits = currencyDigits(currency)
  const padded = amount.padStart(digits + 1, '0')
  return digits ? `${padded.slice(0, -digits)}.${padded.slice(-digits)}` : padded
}

/** Presentation only. Exact integer strings in; no floating-point quote arithmetic or provider authority. */
export function formatMoney(money: Money): string {
  if (
    typeof money?.amount_minor !== 'string' ||
    !/^(0|[1-9][0-9]{0,17})$/.test(money.amount_minor)
  ) {
    throw new Error('Invalid minor-unit amount')
  }
  if (
    typeof money.currency !== 'string' ||
    !/^[A-Z]{3}$/.test(money.currency) ||
    typeof Intl.supportedValuesOf !== 'function' ||
    !Intl.supportedValuesOf('currency').includes(money.currency) ||
    money.currency === 'XXX' ||
    money.currency === 'XTS'
  ) {
    throw new Error('Currency metadata unavailable')
  }
  const digits = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: money.currency,
  }).resolvedOptions().maximumFractionDigits
  if (digits === undefined) throw new Error('Currency exponent unavailable')
  const padded = money.amount_minor.padStart(digits + 1, '0')
  const whole = digits ? padded.slice(0, -digits) : padded
  const grouped = new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(BigInt(whole))
  return `${money.currency} ${grouped}${digits ? `.${padded.slice(-digits)}` : ''}`
}

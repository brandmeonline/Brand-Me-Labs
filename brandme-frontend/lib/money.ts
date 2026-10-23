export type Money = { amount_minor: string; currency: string }

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

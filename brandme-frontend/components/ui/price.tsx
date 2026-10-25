import { formatMoney, type Money } from '../../lib/money'

export function Price({ money }: { money: Money | null }) {
  if (!money) return <span className="bm-price">Price unavailable</span>
  try {
    return <span className="bm-price">{formatMoney(money)}</span>
  } catch {
    return <span className="bm-price">Price unavailable</span>
  }
}

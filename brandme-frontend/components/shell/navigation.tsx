import {
  UserCircle,
  Heart,
  Home,
  Shirt,
  Sparkles,
  Bell,
  Gift,
  SlidersHorizontal,
  ShoppingBag,
  Database,
  Link2,
  MessageCircle,
} from 'lucide-react'
export const primaryNavigation = [
  { href: '/discover', label: 'Shops', icon: ShoppingBag },
  { href: '/social', label: 'Social', icon: Heart },
  { href: '/closet', label: 'Closet', icon: Shirt },
] as const
export const secondaryNavigation = [
  { href: '/today', label: 'Today', icon: Home },
  { href: '/style', label: 'Style', icon: Sparkles },
  { href: '/me', label: 'Me', icon: UserCircle },
  { href: '/circle', label: 'My circle', icon: Heart },
  { href: '/assistant', label: 'My Assistant', icon: MessageCircle },
  { href: '/rewards', label: 'Rewards', icon: Gift },
  { href: '/orders', label: 'Orders', icon: ShoppingBag },
  { href: '/inbox', label: 'Inbox', icon: Bell },
  { href: '/me/data', label: 'My Data', icon: Database },
  { href: '/me/connections', label: 'Connections', icon: Link2 },
  { href: '/settings', label: 'Settings', icon: SlidersHorizontal },
] as const
export const allNavigation = [...primaryNavigation, ...secondaryNavigation]

export function isActiveRoute(path: string, href: string): boolean {
  if (href === '/social' && (path === '/circle' || path.startsWith('/circle/'))) return true
  if (href === '/discover' && path.startsWith('/products/')) return true
  return path === href || path.startsWith(`${href}/`)
}

/** Prefer the closest destination; room aliases only fill a set without one. */
export function currentNavigationItem<T extends { href: string }>(
  path: string,
  items: readonly T[],
): T | undefined {
  let closest: T | undefined
  for (const item of items) {
    if (
      (path === item.href || path.startsWith(`${item.href}/`)) &&
      (!closest || item.href.length > closest.href.length)
    ) {
      closest = item
    }
  }
  return closest || items.find((item) => isActiveRoute(path, item.href))
}

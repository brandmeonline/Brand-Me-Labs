import {
  UserCircle,
  Compass,
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
  { href: '/today', label: 'Today', icon: Home },
  { href: '/closet', label: 'Closet', icon: Shirt },
  { href: '/style', label: 'Style', icon: Sparkles },
  { href: '/circle', label: 'Circle', icon: Heart },
  { href: '/me', label: 'Me', icon: UserCircle },
] as const
export const secondaryNavigation = [
  { href: '/discover', label: 'Discover', icon: Compass },
  { href: '/assistant', label: 'My Assistant', icon: MessageCircle },
  { href: '/rewards', label: 'Rewards', icon: Gift },
  { href: '/orders', label: 'Orders', icon: ShoppingBag },
  { href: '/inbox', label: 'Inbox', icon: Bell },
  { href: '/me/data', label: 'My Data', icon: Database },
  { href: '/me/connections', label: 'Connections', icon: Link2 },
  { href: '/settings', label: 'Settings', icon: SlidersHorizontal },
] as const
export function isActiveRoute(path: string, href: string): boolean {
  return path === href || path.startsWith(`${href}/`)
}

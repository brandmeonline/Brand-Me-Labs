import Link from 'next/link'
import { Shield } from 'lucide-react'

export default function Header() {
  return (
    <header className="border-b border-gray-900 bg-black">
      <div className="max-w-screen-xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          <Link href="/shop" className="text-2xl font-bold tracking-tight hover:text-gray-300 transition">
            Brand.Me
          </Link>

          <nav className="flex items-center gap-8">
            <Link href="/shop" className="text-sm font-medium hover:text-gray-400 transition">
              Shop
            </Link>
            <Link href="/stash" className="text-sm font-medium hover:text-gray-400 transition">
              Stash
            </Link>
            <Link href="/scan" className="text-sm font-medium hover:text-gray-400 transition">
              Scan
            </Link>
          </nav>

          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-900 rounded-full border border-gray-800">
            <Shield className="w-4 h-4 text-green-400" />
            <span className="text-xs font-medium text-gray-300">Integrity</span>
          </div>
        </div>
      </div>
    </header>
  )
}

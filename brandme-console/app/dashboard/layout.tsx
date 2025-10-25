/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Dashboard Layout
 * ================
 * Layout for Governance Console dashboard pages
 */

import Link from 'next/link';
import { Shield, Users, AlertTriangle, Eye, Home } from 'lucide-react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-gray-50 dark:bg-gray-900">
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center border-b px-6">
            <Link href="/" className="flex items-center space-x-2">
              <Shield className="h-6 w-6" />
              <span className="font-bold">Brand.Me</span>
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-3 py-4">
            <Link
              href="/dashboard"
              className="flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Home className="h-5 w-5" />
              <span>Dashboard</span>
            </Link>

            <Link
              href="/dashboard/scans"
              className="flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Users className="h-5 w-5" />
              <span>All Scans</span>
            </Link>

            <Link
              href="/dashboard/escalations"
              className="flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <AlertTriangle className="h-5 w-5" />
              <span>Escalations</span>
            </Link>

            <Link
              href="/dashboard/reveal"
              className="flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <Eye className="h-5 w-5" />
              <span>Controlled Reveals</span>
            </Link>
          </nav>

          {/* Footer */}
          <div className="border-t p-4">
            <div className="text-xs text-muted-foreground">
              <p className="font-medium">Governance Console</p>
              <p className="mt-1">ROLE_GOVERNANCE</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="container mx-auto p-8">{children}</div>
      </main>
    </div>
  );
}

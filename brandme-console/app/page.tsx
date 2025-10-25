/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Landing Page
 * ============
 * Home page with links to Governance Console and Transparency Portal
 */

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, Eye, Lock, Globe } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      <header className="border-b bg-white dark:bg-gray-950">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Shield className="h-8 w-8 text-primary" />
              <h1 className="text-2xl font-bold">Brand.Me</h1>
            </div>
            <div className="text-sm text-muted-foreground">
              v1.0.0
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-16">
        <div className="max-w-4xl mx-auto text-center mb-16">
          <h2 className="text-4xl font-bold mb-4">
            Privacy-Preserving Garment Provenance
          </h2>
          <p className="text-xl text-muted-foreground">
            Verifiable identity, authenticity, and cultural expression through fashion
            with consent-driven visibility
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {/* Governance Console Card */}
          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-center space-x-2 mb-2">
                <Lock className="h-6 w-6 text-primary" />
                <CardTitle>Governance Console</CardTitle>
              </div>
              <CardDescription>
                Internal dashboard for compliance and governance teams
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>View all scans and policy decisions</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Handle escalations and flagged content</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Controlled reveals with dual approval</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Full audit trail visibility</span>
                </li>
              </ul>
              <Link href="/dashboard">
                <Button className="w-full">
                  Access Governance Console
                </Button>
              </Link>
              <p className="text-xs text-muted-foreground text-center">
                Requires: ROLE_GOVERNANCE or ROLE_COMPLIANCE
              </p>
            </CardContent>
          </Card>

          {/* Transparency Portal Card */}
          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-center space-x-2 mb-2">
                <Globe className="h-6 w-6 text-primary" />
                <CardTitle>Transparency Portal</CardTitle>
              </div>
              <CardDescription>
                Public verification portal for garment authenticity
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Public proof of authenticity</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Creator attribution and origin</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>ESG verification proof</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>No private data exposure</span>
                </li>
              </ul>
              <Link href="/proof">
                <Button variant="outline" className="w-full">
                  View Public Proofs
                </Button>
              </Link>
              <p className="text-xs text-muted-foreground text-center">
                No authentication required
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Features Section */}
        <div className="mt-16 max-w-5xl mx-auto">
          <h3 className="text-2xl font-bold text-center mb-8">
            Platform Features
          </h3>
          <div className="grid md:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Dual Blockchain</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Cardano for public provenance, Midnight for private ownership data
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Consent-Driven</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Three-tier visibility: public, friends_only, private
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Tamper-Evident</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Hash-chained audit logs with immutable blockchain anchoring
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>

      <footer className="border-t mt-24">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center text-sm text-muted-foreground">
            <p>© 2025 Brand.Me, Inc. All rights reserved.</p>
            <p className="mt-2">
              Built with privacy, consent, and transparency
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

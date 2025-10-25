/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Public Proof Page
 * =================
 * Transparency Portal - Public proof display (no auth required)
 */

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle, ExternalLink, Shield } from 'lucide-react';
import { getPublicProof, getErrorMessage } from '@/lib/api';

export default function ProofPage() {
  const params = useParams();
  const scanId = params.scanId as string;
  const [proof, setProof] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchProof() {
      try {
        setLoading(true);
        const data = await getPublicProof(scanId);
        setProof(data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }

    fetchProof();
  }, [scanId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center">
        <p className="text-muted-foreground">Loading proof...</p>
      </div>
    );
  }

  if (error || !proof) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Proof Not Found</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{error || 'This scan does not exist or is not public.'}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      {/* Header */}
      <header className="border-b bg-white dark:bg-gray-950">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center space-x-2">
            <Shield className="h-8 w-8 text-primary" />
            <h1 className="text-2xl font-bold">Brand.Me Transparency Portal</h1>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-16">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Title */}
          <div className="text-center">
            <h2 className="text-3xl font-bold mb-2">Garment Authenticity Proof</h2>
            <p className="text-muted-foreground">Verified on blockchain</p>
          </div>

          {/* Authenticity Status */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Authenticity Status</CardTitle>
                {proof.authenticity?.verified ? (
                  <CheckCircle className="h-6 w-6 text-green-600" />
                ) : (
                  <XCircle className="h-6 w-6 text-red-600" />
                )}
              </div>
            </CardHeader>
            <CardContent>
              <Badge variant={proof.authenticity?.verified ? 'success' : 'destructive'} className="text-lg px-4 py-2">
                {proof.authenticity?.verified ? 'AUTHENTIC' : 'COUNTERFEIT WARNING'}
              </Badge>
              <p className="text-sm text-muted-foreground mt-4">
                Hash: <code className="text-xs">{proof.authenticity?.hash}</code>
              </p>
            </CardContent>
          </Card>

          {/* Creator Attribution */}
          {proof.creator && (
            <Card>
              <CardHeader>
                <CardTitle>Creator Attribution</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div>
                  <p className="text-sm font-medium">Creator</p>
                  <p className="text-muted-foreground">{proof.creator.creator_name}</p>
                </div>
                <div>
                  <p className="text-sm font-medium">Created</p>
                  <p className="text-muted-foreground">
                    {new Date(proof.creator.created_at).toLocaleDateString()}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* ESG Verification */}
          {proof.esg && (
            <Card>
              <CardHeader>
                <CardTitle>ESG Verification</CardTitle>
                <CardDescription>Environmental, Social, Governance</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <span className="font-medium">ESG Score</span>
                  <Badge variant="success" className="text-lg">
                    {proof.esg.score}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Blockchain Proof */}
          <Card>
            <CardHeader>
              <CardTitle>Blockchain Verification</CardTitle>
              <CardDescription>Immutable proof on Cardano blockchain</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm font-medium mb-2">Transaction Hash</p>
                <div className="flex items-center space-x-2">
                  <code className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded flex-1 overflow-x-auto">
                    {proof.cardano_tx_hash}
                  </code>
                  <a
                    href={`${process.env.NEXT_PUBLIC_CARDANO_EXPLORER_URL}/transaction/${proof.cardano_tx_hash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline flex items-center"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </div>
              </div>

              <div>
                <p className="text-sm font-medium mb-2">Policy Version</p>
                <code className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded block">
                  {proof.policy_version}
                </code>
              </div>

              <div>
                <p className="text-sm font-medium mb-2">Scan ID</p>
                <code className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded block">
                  {scanId}
                </code>
              </div>
            </CardContent>
          </Card>

          {/* Privacy Notice */}
          <Card className="border-blue-200 bg-blue-50 dark:bg-blue-950">
            <CardHeader>
              <CardTitle className="text-blue-900 dark:text-blue-100">Privacy Notice</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-blue-800 dark:text-blue-200">
                This proof displays only PUBLIC information. Private ownership and pricing data
                are stored encrypted on Midnight blockchain and are never exposed publicly.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>

      <footer className="border-t mt-24">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center text-sm text-muted-foreground">
            <p>© 2025 Brand.Me, Inc. All rights reserved.</p>
            <p className="mt-2">Powered by Cardano & Midnight blockchains</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

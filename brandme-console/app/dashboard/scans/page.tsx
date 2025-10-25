/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Scans List Page
 * ===============
 * View all scans with filtering and search
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';
import { getScans, type Scan, getErrorMessage } from '@/lib/api';

export default function ScansPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchScans() {
      try {
        setLoading(true);
        const data = await getScans({ limit: 50 });
        setScans(data.scans);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }

    fetchScans();
  }, []);

  function getDecisionBadge(decision: string) {
    switch (decision) {
      case 'allow':
        return <Badge variant="success">Allowed</Badge>;
      case 'deny':
        return <Badge variant="destructive">Denied</Badge>;
      case 'escalate':
        return <Badge variant="warning">Escalated</Badge>;
      default:
        return <Badge variant="secondary">{decision}</Badge>;
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading scans...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">All Scans</h1>
        <p className="text-muted-foreground">View and manage all garment scans</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Scans ({scans.length})</CardTitle>
          <CardDescription>Click on a scan to view detailed information</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {scans.map((scan) => (
              <Link
                key={scan.scan_id}
                href={`/dashboard/scan/${scan.scan_id}`}
                className="block border-b pb-4 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-900 rounded p-4 -m-4"
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center space-x-2">
                      <p className="font-medium">{scan.scan_id}</p>
                      {getDecisionBadge(scan.decision)}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Garment: {scan.garment_id}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Scope: {scan.resolved_scope} | Policy: {scan.policy_version}
                    </p>
                    {scan.cardano_tx_hash && (
                      <div className="flex items-center space-x-1 text-sm">
                        <span className="text-muted-foreground">Cardano:</span>
                        <code className="text-xs">{scan.cardano_tx_hash.substring(0, 16)}...</code>
                        <ExternalLink className="h-3 w-3" />
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-muted-foreground">
                      {new Date(scan.scanned_at).toLocaleDateString()}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(scan.scanned_at).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

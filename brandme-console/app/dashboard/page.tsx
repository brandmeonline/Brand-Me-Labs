/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Dashboard Overview
 * ==================
 * Main dashboard with stats and recent activity
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function DashboardPage() {
  // In production, fetch real data from API
  const stats = {
    totalScans: 1247,
    allowed: 1089,
    denied: 132,
    escalations: 26,
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Governance Console</h1>
        <p className="text-muted-foreground">
          Monitor scans, handle escalations, and manage controlled reveals
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Scans</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalScans.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Last 30 days</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Allowed</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {stats.allowed.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">
              {((stats.allowed / stats.totalScans) * 100).toFixed(1)}% approval rate
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Denied</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {stats.denied.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">
              {((stats.denied / stats.totalScans) * 100).toFixed(1)}% denial rate
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Escalations</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">
              {stats.escalations.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">Require review</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Latest scans and policy decisions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center justify-between border-b pb-4 last:border-0">
                <div>
                  <p className="font-medium">Scan #{1247 - i + 1}</p>
                  <p className="text-sm text-muted-foreground">
                    Garment: garment-{Math.random().toString(36).substr(2, 9)}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-sm text-muted-foreground">2 min ago</span>
                  <div className={`rounded-full px-2 py-1 text-xs ${i % 3 === 0 ? 'bg-green-100 text-green-700' : i % 3 === 1 ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>
                    {i % 3 === 0 ? 'Allowed' : i % 3 === 1 ? 'Denied' : 'Escalated'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

import { getEscalations } from '@/lib/demoData'
import { CheckCircle, XCircle, Clock } from 'lucide-react'

export default async function GovernancePage() {
  const escalations = await getEscalations()

  return (
    <div className="space-y-8 bg-gray-950 -m-6 p-6 min-h-screen">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-gray-200">Governance Console</h1>
        <p className="text-gray-400">Review and approve escalated scan requests</p>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-800 border-b border-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Scan ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Region
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Reason
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {escalations.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    No pending escalations
                  </td>
                </tr>
              ) : (
                escalations.map((escalation, index) => (
                  <tr key={index} className="hover:bg-gray-800/50 transition">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-300">
                      {escalation.scan_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                      {escalation.region_code}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-300 max-w-md">
                      {escalation.reason}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                      {new Date(escalation.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                      <button className="inline-flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-medium transition">
                        <CheckCircle className="w-3.5 h-3.5" />
                        Approve
                      </button>
                      <button className="inline-flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-medium transition">
                        <XCircle className="w-3.5 h-3.5" />
                        Deny
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-gray-500">
        <Clock className="w-4 h-4" />
        <span>Auto-refreshing every 30 seconds (stub)</span>
      </div>
    </div>
  )
}

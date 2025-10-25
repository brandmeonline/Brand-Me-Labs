/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * API Client
 * ==========
 * HTTP client for Brand.Me backend services
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost:3000';
const COMPLIANCE_SERVICE_URL = process.env.NEXT_PUBLIC_COMPLIANCE_SERVICE_URL || 'http://localhost:8102';
const KNOWLEDGE_SERVICE_URL = process.env.NEXT_PUBLIC_KNOWLEDGE_SERVICE_URL || 'http://localhost:8101';
const CHAIN_SERVICE_URL = process.env.NEXT_PUBLIC_CHAIN_SERVICE_URL || 'http://localhost:3001';

/**
 * Create API client instance
 */
function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({
    baseURL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Request interceptor for adding auth token
  client.interceptors.request.use(
    (config) => {
      // In production, get token from NextAuth or cookies
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  // Response interceptor for error handling
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response?.status === 401) {
        // Handle unauthorized - redirect to login
        if (typeof window !== 'undefined') {
          window.location.href = '/auth/signin';
        }
      }
      return Promise.reject(error);
    }
  );

  return client;
}

// API clients for different services
export const gatewayClient = createApiClient(GATEWAY_URL);
export const complianceClient = createApiClient(COMPLIANCE_SERVICE_URL);
export const knowledgeClient = createApiClient(KNOWLEDGE_SERVICE_URL);
export const chainClient = createApiClient(CHAIN_SERVICE_URL);

/**
 * Type definitions
 */

export interface Scan {
  scan_id: string;
  garment_id: string;
  scanner_user_id: string;
  resolved_scope: string;
  decision: string;
  policy_version: string;
  cardano_tx_hash: string | null;
  midnight_tx_hash: string | null;
  crosschain_root_hash: string | null;
  scanned_at: string;
}

export interface ScanDetail extends Scan {
  facets: Facet[];
  audit_trail: AuditEntry[];
  policy_detail: PolicyDetail;
}

export interface Facet {
  facet_id: string;
  facet_type: string;
  facet_payload_preview: any;
  visibility_scope: string;
}

export interface AuditEntry {
  audit_id: string;
  created_at: string;
  actor_type: string;
  action_type: string;
  decision_summary: string;
  decision_detail: any;
  policy_version: string;
  entry_hash: string;
  prev_entry_hash: string | null;
}

export interface PolicyDetail {
  policy_version: string;
  regional_code: string;
  rules: any;
}

/**
 * API Functions
 */

// Scans
export async function getScans(params?: {
  limit?: number;
  offset?: number;
  decision?: string;
}) {
  const response = await complianceClient.get<{ scans: Scan[] }>('/scans', { params });
  return response.data;
}

export async function getScanDetail(scanId: string) {
  const response = await complianceClient.get<ScanDetail>(`/scan/${scanId}`);
  return response.data;
}

export async function getEscalations() {
  const response = await complianceClient.get<{ scans: Scan[] }>('/scans', {
    params: { decision: 'escalate' },
  });
  return response.data;
}

// Audit
export async function getAuditTrail(scanId: string) {
  const response = await complianceClient.get<{ audit_trail: AuditEntry[] }>(`/audit/${scanId}`);
  return response.data;
}

export async function getAuditExplanation(scanId: string) {
  const response = await complianceClient.get<{ explanation: string }>(`/audit/${scanId}/explain`);
  return response.data;
}

// Blockchain
export async function verifyBlockchainTx(txHash: string, chain: 'cardano' | 'midnight') {
  const response = await chainClient.post<{ is_valid: boolean }>('/tx/verify', {
    tx_hash: txHash,
    chain,
  });
  return response.data;
}

export async function verifyCrossChainRoot(rootHash: string) {
  const response = await chainClient.post<{ is_consistent: boolean }>('/tx/verify-root', {
    crosschain_root_hash: rootHash,
  });
  return response.data;
}

// Garment/Passport
export async function getGarmentPassport(garmentId: string, scope: string = 'public') {
  const response = await knowledgeClient.get<{ facets: Facet[] }>(`/garment/${garmentId}/passport`, {
    params: { scope },
  });
  return response.data;
}

// Controlled Reveal (requires dual approval)
export async function requestControlledReveal(data: {
  scan_id: string;
  requester_id: string;
  reason: string;
  approvals: string[];
}) {
  const response = await complianceClient.post<{ reveal_id: string; status: string }>('/reveal/request', data);
  return response.data;
}

export async function approveReveal(revealId: string, approverId: string) {
  const response = await complianceClient.post(`/reveal/${revealId}/approve`, {
    approver_id: approverId,
  });
  return response.data;
}

// Public proof (no auth required)
export async function getPublicProof(scanId: string) {
  const response = await axios.get(`${COMPLIANCE_SERVICE_URL}/proof/${scanId}`);
  return response.data;
}

/**
 * Error handling utility
 */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.message || error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unknown error occurred';
}

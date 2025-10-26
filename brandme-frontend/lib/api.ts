import { v4 as uuidv4 } from 'uuid'

/**
 * Generates a unique request ID for distributed tracing
 */
export function getRequestId(): string {
  return uuidv4()
}

/**
 * Calls backend service with automatic request ID propagation
 */
export async function callBackendWithRequestId(
  url: string,
  options: RequestInit = {},
  requestId?: string
): Promise<Response> {
  const id = requestId || getRequestId()

  const headers = {
    'X-Request-Id': id,
    'Content-Type': 'application/json',
    ...options.headers,
  }

  return fetch(url, {
    ...options,
    headers,
  })
}

/**
 * Backend API client with request ID handling
 */
export class BrandMeClient {
  private baseUrl: string

  constructor(baseUrl: string = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') {
    this.baseUrl = baseUrl
  }

  async post<T>(path: string, body: any, requestId?: string): Promise<T> {
    const response = await callBackendWithRequestId(
      `${this.baseUrl}${path}`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      requestId
    )

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  async get<T>(path: string, requestId?: string): Promise<T> {
    const response = await callBackendWithRequestId(
      `${this.baseUrl}${path}`,
      {
        method: 'GET',
      },
      requestId
    )

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }
}

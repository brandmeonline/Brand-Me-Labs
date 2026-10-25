import { proxyGateway } from '@/lib/server/gateway-proxy'
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
type Context = { params: Promise<{ path: string[] }> }
async function relay(request: Request, context: Context) {
  return proxyGateway(request, (await context.params).path, process.env)
}
export { relay as GET, relay as POST, relay as PATCH, relay as PUT, relay as DELETE, relay as HEAD }

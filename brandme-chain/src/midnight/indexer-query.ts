/** Bounded, server-only indexer requests. Provider URLs may contain credentials. */
export async function indexerQuery(url: string, query: string, variables: object,
  doFetch: typeof fetch = fetch, maxBytes = 1024 * 1024): Promise<unknown> {
  const res = await doFetch(url, {
    method: 'POST', headers: { 'content-type': 'application/json' }, redirect: 'error',
    signal: AbortSignal.timeout(5000), body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) { await res.body?.cancel(); throw new Error('indexer unavailable'); }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('empty indexer response');
  const chunks: Uint8Array[] = []; let bytes = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) throw new Error('indexer response too large');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

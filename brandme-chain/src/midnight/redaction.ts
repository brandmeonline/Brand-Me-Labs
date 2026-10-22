/** Sanitize provider errors before they reach logs, operation history, or evidence. */
export function redactProviderSecrets(text: string, secrets: readonly string[] = []): string {
  let safe = text.replace(/([?&]project_id=)[^\s&"'\\<>]+/gi, '$1[REDACTED]')
    .replace(/night(?:preprod|mainnet)[A-Za-z0-9_-]+/g, '[REDACTED]');
  for (const secret of secrets) if (secret) safe = safe.split(secret).join('[REDACTED]');
  return safe;
}

import { Writable } from 'node:stream';
import pino from 'pino';
import { describe, expect, it } from 'vitest';
import { REDACT_PATHS } from '../config/logger';

function capture() {
  const lines: string[] = [];
  const stream = new Writable({ write(chunk, _enc, cb) { lines.push(chunk.toString()); cb(); } });
  return { log: pino({ redact: { paths: REDACT_PATHS, censor: '[REDACTED]' } }, stream), lines };
}

describe('log redaction', () => {
  it('redacts the identifiers the legacy /scan route logs', () => {
    const { log, lines } = capture();
    log.info({ scan_id: 's1', scanner_user_id: 'member-123', garment_tag: 'TAG-SECRET', region_code: 'us-east1' }, 'Scan requested');
    const out = JSON.parse(lines[0]);
    expect(out.scanner_user_id).toBe('[REDACTED]');
    expect(out.garment_tag).toBe('[REDACTED]');
    expect(out.scan_id).toBe('s1');
    expect(lines[0]).not.toContain('member-123');
    expect(lines[0]).not.toContain('TAG-SECRET');
  });

  it('redacts nested identifiers, session headers and secrets', () => {
    const { log, lines } = capture();
    log.info({
      ctx: { userId: 'u1', email: 'a@b.example', member_id: 'm1', csrf_token: 'c1' },
      req: { headers: { cookie: 'bm_session=abc', authorization: 'Bearer t', 'x-csrf-token': 'c2' } },
    }, 'x');
    for (const leaked of ['u1', 'a@b.example', 'm1', 'c1', 'bm_session=abc', 'Bearer t', 'c2']) {
      expect(lines[0]).not.toContain(leaked);
    }
  });
});

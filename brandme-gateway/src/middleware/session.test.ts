import { describe, expect, it } from 'vitest';
import { parseCookies, SESSION_COOKIE } from './session';

describe('parseCookies', () => {
  it('decodes percent-encoded values', () => {
    expect(parseCookies(`${SESSION_COOKIE}=a%2Bb; other=1`)).toEqual({ [SESSION_COOKIE]: 'a+b', other: '1' });
  });

  it('keeps a malformed foreign cookie raw instead of throwing', () => {
    const cookies = parseCookies(`_ga=GA1.%E0%A4%A; promo=50%off; ${SESSION_COOKIE}=abc`);
    expect(cookies[SESSION_COOKIE]).toBe('abc');
    expect(cookies.promo).toBe('50%off');
  });

  it('ignores parts without a name', () => {
    expect(parseCookies('=x; ; a=1')).toEqual({ a: '1' });
  });
});

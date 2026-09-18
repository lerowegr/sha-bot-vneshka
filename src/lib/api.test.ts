import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveResult } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('saving results', () => {
  it('does not send a request outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await saveResult('score_7')).toBe('preview'); expect(fetch).not.toHaveBeenCalled();
  });
  it('sends only signed initData and the result', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }); vi.stubGlobal('fetch', fetch);
    expect(await saveResult('score_10')).toBe('saved');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ initData: 'signed', result: 'score_10' });
  });
  it.each([401, 503])('handles HTTP %s without claiming success', async status => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, ok: false }));
    expect(await saveResult('score_5')).toBe(status === 401 ? 'expired' : 'failed');
  });
  it('allows retry after a network error', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) }));
    expect(await saveResult('score_5')).toBe('failed'); expect(await saveResult('score_5')).toBe('saved');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveResult, type Profile } from './api';
const PROFILE: Profile = { last_name: 'Иванова', first_name: 'Анна', middle_name: 'Сергеевна', course: '2', student_id: '123456', phone: '+79161234567' };
afterEach(() => vi.unstubAllGlobals());
describe('saving results', () => {
  it('does not send a request outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await saveResult('score_7', PROFILE)).toBe('preview'); expect(fetch).not.toHaveBeenCalled();
  });
  it('sends signed initData, the result and the profile', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }); vi.stubGlobal('fetch', fetch);
    expect(await saveResult('score_10', PROFILE)).toBe('saved');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ initData: 'signed', result: 'score_10', profile: PROFILE });
  });
  it.each([401, 503])('handles HTTP %s without claiming success', async status => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, ok: false }));
    expect(await saveResult('score_5', PROFILE)).toBe(status === 401 ? 'expired' : 'failed');
  });
  it('reports a repeated attempt as duplicate', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 409, ok: false }));
    expect(await saveResult('score_5', PROFILE)).toBe('duplicate');
  });
  it('allows retry after a network error', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) }));
    expect(await saveResult('score_5', PROFILE)).toBe('failed'); expect(await saveResult('score_5', PROFILE)).toBe('saved');
  });
});

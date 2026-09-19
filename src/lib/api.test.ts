import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchOverview, fetchStatus, runRaffle, saveQuiz, type Profile } from './api';
const PROFILE: Profile = { last_name: 'Иванова', first_name: 'Анна', middle_name: 'Сергеевна', course: 'b2', faculty: 'СНиМК', student_id: '123456', phone: '+79161234567' };
const ANSWERS = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0];
const TIMES = [1200, 900, 1500, 800, 1100, 950, 1300, 700, 1000, 600];
afterEach(() => vi.unstubAllGlobals());
describe('saving quizzes', () => {
  it('does not send a request outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: 'preview' }); expect(fetch).not.toHaveBeenCalled();
  });
  it('sends signed initData, canonical answers, times and the profile', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, score: 10 }) }); vi.stubGlobal('fetch', fetch);
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: 'saved', score: 10 });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ initData: 'signed', answers: ANSWERS, times: TIMES, profile: PROFILE });
  });
  it.each([401, 503])('handles HTTP %s without claiming success', async status => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, ok: false }));
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: status === 401 ? 'expired' : 'failed' });
  });
  it('reports a repeated attempt as duplicate', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 409, ok: false }));
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: 'duplicate' });
  });
  it('allows retry after a network error', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, score: 7 }) }));
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: 'failed' });
    expect(await saveQuiz(ANSWERS, TIMES, PROFILE)).toEqual({ status: 'saved', score: 7 });
  });
});
describe('admin overview', () => {
  it('returns null outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await fetchOverview()).toBeNull(); expect(fetch).not.toHaveBeenCalled();
  });
  it('returns the dashboard payload for admins', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const payload = { ok: true, total: 2 };
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload }); vi.stubGlobal('fetch', fetch);
    expect(await fetchOverview()).toEqual(payload);
    expect(fetch.mock.calls[0][0]).toContain('/api/admin/overview?initData=signed');
  });
  it('returns null when access is denied', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403 }));
    expect(await fetchOverview()).toBeNull();
  });
});
describe('quiz status', () => {
  it('returns null outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await fetchStatus()).toBeNull(); expect(fetch).not.toHaveBeenCalled();
  });
  it('returns the lock state for participants', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const payload = { ok: true, completed: true, score: '7', result: 'score_7', is_admin: false };
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload }); vi.stubGlobal('fetch', fetch);
    expect(await fetchStatus()).toEqual(payload);
    expect(fetch.mock.calls[0][0]).toContain('/api/quiz/status?initData=signed');
  });
  it('returns null on errors', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await fetchStatus()).toBeNull();
  });
});
describe('raffle', () => {
  it('returns null outside Telegram', async () => {
    vi.stubGlobal('window', {});
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    expect(await runRaffle(1)).toBeNull(); expect(fetch).not.toHaveBeenCalled();
  });
  it('posts the draw and returns winners', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    const winners = [{ telegram_user_id: 1 }];
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, draw_id: 3, winners }) }); vi.stubGlobal('fetch', fetch);
    expect(await runRaffle(2)).toEqual({ draw_id: 3, winners });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ initData: 'signed', count: 2 });
  });
  it('returns null when denied', async () => {
    vi.stubGlobal('window', { Telegram: { WebApp: { initData: 'signed' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403 }));
    expect(await runRaffle(1)).toBeNull();
  });
});

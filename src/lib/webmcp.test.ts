import { afterEach, expect, it, vi } from 'vitest';
import { registerQuizTool } from './webmcp';
const PROFILE = { last_name: 'Иванова', first_name: 'Анна', middle_name: 'Сергеевна', course: '2', student_id: '123456', phone: '+79161234567' };
const ANSWERS = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0];
const TIMES = [1200, 900, 1500, 800, 1100, 950, 1300, 700, 1000, 600];
afterEach(() => vi.unstubAllGlobals());
it('validates the optional tool contract and cleans up registration', async () => {
  const registerTool = vi.fn();
  vi.stubGlobal('document', { modelContext: { registerTool } });
  const complete = vi.fn().mockResolvedValue({ score: 7, saved: 'preview' });
  const cleanup = registerQuizTool(complete);
  const [tool, options] = registerTool.mock.calls[0];
  expect(tool.name).toBe('complete_sha_quiz');
  expect(tool.annotations.readOnlyHint).toBe(false);
  await expect(tool.execute({ answers: ANSWERS, times: TIMES })).rejects.toThrow();
  await expect(tool.execute({ answers: ANSWERS, times: TIMES, profile: { ...PROFILE, phone: '' } })).rejects.toThrow();
  expect(complete).not.toHaveBeenCalled();
  expect(await tool.execute({ answers: ANSWERS, times: TIMES, profile: PROFILE })).toEqual({ score: 7, saved: 'preview' });
  expect(complete).toHaveBeenCalledWith(ANSWERS, undefined, PROFILE, TIMES);
  cleanup(); expect(options.signal.aborted).toBe(true);
});
it('does nothing in browsers without WebMCP', () => {
  vi.stubGlobal('document', {});
  expect(registerQuizTool(vi.fn())).toBeTypeOf('function');
});

import { afterEach, expect, it, vi } from 'vitest';
import { registerQuizTool } from './webmcp';
const PROFILE = { last_name: 'Иванова', first_name: 'Анна', middle_name: 'Сергеевна', course: '2', student_id: '123456', phone: '+79161234567' };
afterEach(() => vi.unstubAllGlobals());
it('validates the optional tool contract and cleans up registration', async () => {
  const registerTool = vi.fn();
  vi.stubGlobal('document', { modelContext: { registerTool } });
  const complete = vi.fn().mockResolvedValue({ result: 'score_7', score: 7, saved: 'preview' });
  const cleanup = registerQuizTool(complete);
  const [tool, options] = registerTool.mock.calls[0];
  expect(tool.name).toBe('complete_sha_quiz');
  expect(tool.annotations.readOnlyHint).toBe(false);
  await expect(tool.execute({ answers: Array(10).fill(0) })).rejects.toThrow();
  await expect(tool.execute({ answers: Array(10).fill(0), profile: { ...PROFILE, phone: '' } })).rejects.toThrow();
  expect(complete).not.toHaveBeenCalled();
  const answers = Array(10).fill(0);
  expect(await tool.execute({ answers, profile: PROFILE })).toEqual({ result: 'score_7', score: 7, saved: 'preview' });
  expect(complete).toHaveBeenCalledWith(answers, undefined, PROFILE);
  cleanup(); expect(options.signal.aborted).toBe(true);
});
it('does nothing in browsers without WebMCP', () => {
  vi.stubGlobal('document', {});
  expect(registerQuizTool(vi.fn())).toBeTypeOf('function');
});

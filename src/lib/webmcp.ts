import { TOTAL_QUESTIONS, type Question } from '../data/questions';
import type { Profile } from './api';

const PROFILE_KEYS = ['last_name', 'first_name', 'middle_name', 'course', 'student_id', 'phone'] as const;

type Tool = {
  name: string; title: string; description: string; inputSchema: object;
  annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
  execute(input: unknown): Promise<unknown>;
};
declare global {
  interface Document {
    modelContext?: { registerTool(tool: Tool, options?: { signal: AbortSignal }): void | Promise<void> };
  }
}

export function registerQuizTool(complete: (answers: number[], qs?: readonly Question[], profile?: Profile | null) => Promise<{ result: string; score: number; saved: string }>): () => void {
  const context = document.modelContext;
  if (!context?.registerTool) return () => {};
  const controller = new AbortController();
  const tool: Tool = {
    name: 'complete_sha_quiz', title: 'Завершить тест про Школу Актива',
    description: 'Complete the 10-question School of Activ quiz using the user’s chosen answer indices in question order plus their contest profile (name, course, student ID, phone). Shows the score and, inside Telegram, saves it. One attempt per user. Do not invent user answers or profile data.',
    inputSchema: { type: 'object', properties: { answers: { type: 'array', minItems: TOTAL_QUESTIONS, maxItems: TOTAL_QUESTIONS, items: { type: 'integer', minimum: 0, maximum: 4 } }, profile: { type: 'object', properties: { last_name: { type: 'string' }, first_name: { type: 'string' }, middle_name: { type: 'string' }, course: { type: 'string' }, student_id: { type: 'string' }, phone: { type: 'string' } }, required: [...PROFILE_KEYS], additionalProperties: false } }, required: ['answers', 'profile'], additionalProperties: false },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    async execute(input) {
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Expected answers and profile');
      const record = input as Record<string, unknown>;
      if (Object.keys(record).length !== 2 || !('answers' in record) || !('profile' in record)) throw new Error('Expected answers and profile');
      const answers = record.answers;
      if (!Array.isArray(answers) || answers.length !== TOTAL_QUESTIONS || answers.some(answer => !Number.isInteger(answer) || answer < 0 || answer > 4)) throw new Error('Expected ten valid answer indices');
      const profile = record.profile;
      if (!profile || typeof profile !== 'object' || Array.isArray(profile)) throw new Error('Expected profile');
      const entries = Object.entries(profile);
      if (entries.length !== PROFILE_KEYS.length || entries.some(([key, value]) => !PROFILE_KEYS.includes(key as (typeof PROFILE_KEYS)[number]) || typeof value !== 'string' || !value.trim())) throw new Error('Expected a complete profile');
      return complete([...answers], undefined, Object.fromEntries(entries) as unknown as Profile);
    },
  };
  try { void Promise.resolve(context.registerTool(tool, { signal: controller.signal })).catch(() => {}); } catch { /* Optional browser API; the visible quiz remains available. */ }
  return () => controller.abort();
}

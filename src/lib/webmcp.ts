import { TOTAL_QUESTIONS, type Question } from '../data/questions';

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

export function registerQuizTool(complete: (answers: number[], qs?: readonly Question[]) => Promise<{ result: string; score: number; saved: string }>): () => void {
  const context = document.modelContext;
  if (!context?.registerTool) return () => {};
  const controller = new AbortController();
  const tool: Tool = {
    name: 'complete_sha_quiz', title: 'Завершить тест про Школу Актива',
    description: 'Complete the 10-question School of Activ quiz using the user’s chosen answer indices in question order. Shows the score and, inside Telegram, saves it. Do not invent user answers.',
    inputSchema: { type: 'object', properties: { answers: { type: 'array', minItems: TOTAL_QUESTIONS, maxItems: TOTAL_QUESTIONS, items: { type: 'integer', minimum: 0, maximum: 4 } } }, required: ['answers'], additionalProperties: false },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    async execute(input) {
      if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).length !== 1 || !('answers' in input)) throw new Error('Expected answers');
      const answers = input.answers;
      if (!Array.isArray(answers) || answers.length !== TOTAL_QUESTIONS || answers.some(answer => !Number.isInteger(answer) || answer < 0 || answer > 4)) throw new Error('Expected ten valid answer indices');
      return complete([...answers]);
    },
  };
  try { void Promise.resolve(context.registerTool(tool, { signal: controller.signal })).catch(() => {}); } catch { /* Optional browser API; the visible quiz remains available. */ }
  return () => controller.abort();
}

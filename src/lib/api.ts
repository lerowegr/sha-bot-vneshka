import { initData } from './telegram';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'preview' | 'failed' | 'expired' | 'duplicate';
export type Profile = { last_name: string; first_name: string; middle_name: string; course: string; faculty: string; student_id: string; phone: string };
export type SaveOutcome = { status: SaveStatus; score?: number };
export async function saveQuiz(answers: number[], times: number[], profile: Profile): Promise<SaveOutcome> {
  const data = initData();
  if (!data) return { status: 'preview' };
  try {
    const response = await fetch('/api/quiz/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData: data, answers, times, profile }), signal: AbortSignal.timeout(10000) });
    if (response.status === 401) return { status: 'expired' };
    if (response.status === 409) return { status: 'duplicate' };
    if (!response.ok) return { status: 'failed' };
    const body = await response.json();
    return body.ok === true ? { status: 'saved', score: body.score } : { status: 'failed' };
  } catch { return { status: 'failed' }; }
}

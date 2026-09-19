import { initData } from './telegram';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'preview' | 'failed' | 'expired' | 'duplicate';
export type Profile = { last_name: string; first_name: string; middle_name: string; course: string; faculty: string; student_id: string; phone: string };
export type SaveOutcome = { status: SaveStatus; score?: number };
export type OverviewQuestion = { label: string; attempts: number; correct: number; pct: number; avg_ms: number };
export type Winner = {
  telegram_user_id: number; telegram_username: string | null;
  last_name: string | null; first_name: string | null; middle_name: string | null;
  course: string | null; faculty: string | null; student_id: string | null;
  phone: string | null; result: string | null;
};
export type RaffleDraw = { id: number; admin_id: number; asked_count: number; winners: Winner[]; created_at: string };
export type Overview = {
  total: number; avg_score: number;
  by_result: Record<string, number>; by_course: Record<string, number>;
  by_faculty: Record<string, number>; matrix: Record<string, Record<string, number>>;
  questions: OverviewQuestion[];   avg_total_ms: number; timed_count: number;
  eligible: number; dup_phones: number; dup_student_ids: number; raffles: RaffleDraw[];
};
export async function fetchOverview(): Promise<Overview | null> {
  const data = initData();
  if (!data) return null;
  try {
    const response = await fetch(`/api/admin/overview?initData=${encodeURIComponent(data)}`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) return null;
    const body = await response.json();
    return body.ok === true ? (body as Overview) : null;
  } catch { return null; }
}
export type QuizStatus = { completed: boolean; score?: string; result?: string; is_admin: boolean };
export async function runRaffle(count: number): Promise<{ draw_id: number; winners: Winner[] } | null> {
  const data = initData();
  if (!data) return null;
  try {
    const response = await fetch('/api/admin/raffle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData: data, count }), signal: AbortSignal.timeout(15000) });
    if (!response.ok) return null;
    const body = await response.json();
    return body.ok === true ? { draw_id: body.draw_id, winners: body.winners } : null;
  } catch { return null; }
}
export async function fetchStatus(): Promise<QuizStatus | null> {
  const data = initData();
  if (!data) return null;
  try {
    const response = await fetch(`/api/quiz/status?initData=${encodeURIComponent(data)}`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) return null;
    const body = await response.json();
    return body.ok === true ? (body as QuizStatus) : null;
  } catch { return null; }
}
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

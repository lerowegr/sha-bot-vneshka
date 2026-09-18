import { initData } from './telegram';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'preview' | 'failed' | 'expired' | 'duplicate';
export type Profile = { last_name: string; first_name: string; middle_name: string; course: string; student_id: string; phone: string };
export async function saveResult(result: string, profile: Profile): Promise<SaveStatus> {
  const data = initData();
  if (!data) return 'preview';
  try {
    const response = await fetch('/api/quiz/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData: data, result, profile }), signal: AbortSignal.timeout(10000) });
    if (response.status === 401) return 'expired';
    if (response.status === 409) return 'duplicate';
    if (!response.ok) return 'failed';
    const body = await response.json();
    return body.ok === true ? 'saved' : 'failed';
  } catch { return 'failed'; }
}

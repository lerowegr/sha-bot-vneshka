import { initData } from './telegram';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'preview' | 'failed' | 'expired';
export async function saveResult(result: string): Promise<SaveStatus> {
  const data = initData();
  if (!data) return 'preview';
  try {
    const response = await fetch('/api/quiz/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData: data, result }), signal: AbortSignal.timeout(10000) });
    if (response.status === 401) return 'expired';
    if (!response.ok) return 'failed';
    const body = await response.json();
    return body.ok === true ? 'saved' : 'failed';
  } catch { return 'failed'; }
}

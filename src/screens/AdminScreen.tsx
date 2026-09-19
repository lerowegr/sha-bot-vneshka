import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, RotateCcw } from 'lucide-react';
import { fetchOverview, type Overview } from '../lib/api';

const COLORS = ['#2CE719', '#BF2AFF', '#FF8512', '#1C63FF', '#FFCC00', '#F70302'];
const COURSE_ORDER = ['b1', 'b2', 'b3', 'b4', 'm1', 'm2'];
const COURSE_SHORT: Record<string, string> = { b1: 'Бак · 1', b2: 'Бак · 2', b3: 'Бак · 3', b4: 'Бак · 4', m1: 'Маг · 1', m2: 'Маг · 2' };

function fmtSecs(ms: number): string {
  const seconds = ms / 1000;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}м ${(seconds % 60).toFixed(1)}с`;
  return `${seconds.toFixed(1)}с`;
}

function HBar({ label, value, max, color, hint }: { label: string; value: number; max: number; color: string; hint: string }) {
  return <div className="hbar">
    <div className="hbar-top"><span>{label}</span><span>{hint}</span></div>
    <div className="hbar-track"><div className="hbar-fill" style={{ width: `${max ? (value / max) * 100 : 0}%`, background: color }} /></div>
  </div>;
}

export function AdminScreen({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => {
    setFailed(false);
    void fetchOverview().then(result => {
      if (result) setData(result);
      else setFailed(true);
    });
  }, []);
  useEffect(load, [load]);

  if (!data) return <section className="admin-screen">
    <button className="text-button" onClick={onBack}><ArrowLeft size={16} />Назад</button>
    <div className="eyebrow">АДМИНКА · ДАШБОРД</div>
    <h2 data-screen-heading tabIndex={-1}>Как идёт конкурс</h2>
    {failed
      ? <><p className="muted">Не получилось загрузить данные. Дашборд доступен только организаторам: если ты админ — закрой миниапп, открой заново через кнопку бота и нажми «Обновить».</p>
        <button className="primary w-full" onClick={load}><RotateCcw size={18} />Обновить</button></>
      : <p className="muted">Загружаем цифры…</p>}
  </section>;

  const maxScore = Math.max(1, ...Object.values(data.by_result));
  const maxCourse = Math.max(1, ...COURSE_ORDER.map(key => data.by_course[key] ?? 0));
  const faculties = Object.keys(data.by_faculty).sort((a, b) => data.by_faculty[b] - data.by_faculty[a]);
  const maxFaculty = Math.max(1, ...faculties.map(key => data.by_faculty[key]));
  const ranked = [...data.questions]
    .map((question, index) => ({ ...question, number: index + 1 }))
    .sort((a, b) => a.pct - b.pct);
  return <section className="admin-screen">
    <button className="text-button" onClick={onBack}><ArrowLeft size={16} />Назад</button>
    <div className="eyebrow">АДМИНКА · ДАШБОРД</div>
    <h2 data-screen-heading tabIndex={-1}>Как идёт конкурс</h2>
    <div className="stat-cards">
      <div className="stat-card"><strong>{data.total}</strong><span>участников</span></div>
      <div className="stat-card"><strong>{data.avg_score.toFixed(1)}</strong><span>средний балл</span></div>
      <div className="stat-card"><strong>{data.timed_count ? fmtSecs(data.avg_total_ms) : '—'}</strong><span>среднее время</span></div>
    </div>

    <div className="dash-block">
      <div className="eyebrow">БАЛЛЫ 0–10</div>
      <div className="vbars">
        {Array.from({ length: 11 }, (_, score) => {
          const count = data.by_result[String(score)] ?? 0;
          return <div className="vbar" key={score}>
            <div className="vbar-track"><div className="vbar-fill" style={{ height: `${(count / maxScore) * 100}%`, background: COLORS[score % COLORS.length] }} /></div>
            <span className="vbar-label">{score}</span>
            <span className="vbar-count">{count}</span>
          </div>;
        })}
      </div>
    </div>

    <div className="dash-block">
      <div className="eyebrow">КУРСЫ</div>
      {COURSE_ORDER.map((key, i) => {
        const count = data.by_course[key] ?? 0;
        const hint = data.total ? `${count} · ${(count * 100 / data.total).toFixed(1)}%` : `${count}`;
        return <HBar key={key} label={COURSE_SHORT[key]} value={count} max={maxCourse} color={COLORS[i % COLORS.length]} hint={hint} />;
      })}
    </div>

    <div className="dash-block">
      <div className="eyebrow">ФАКУЛЬТЕТЫ</div>
      {faculties.map((name, i) => {
        const count = data.by_faculty[name];
        const hint = data.total ? `${count} · ${(count * 100 / data.total).toFixed(1)}%` : `${count}`;
        return <HBar key={name} label={name} value={count} max={maxFaculty} color={COLORS[i % COLORS.length]} hint={hint} />;
      })}
    </div>

    <div className="dash-block">
      <div className="eyebrow">ФАКУЛЬТЕТ × КУРС</div>
      <div className="matrix-wrap"><table className="matrix">
        <thead><tr><th></th>{COURSE_ORDER.map(key => <th key={key}>{COURSE_SHORT[key]}</th>)}<th>Σ</th></tr></thead>
        <tbody>
          {faculties.map(name => {
            const row = COURSE_ORDER.map(key => data.matrix[name]?.[key] ?? 0);
            const sum = row.reduce((a, b) => a + b, 0);
            if (!sum) return null;
            return <tr key={name}><td>{name}</td>{row.map((count, i) => <td key={i}>{count || '·'}</td>)}<td><strong>{sum}</strong></td></tr>;
          })}
        </tbody>
      </table></div>
    </div>

    <div className="dash-block">
      <div className="eyebrow">ВОПРОСЫ · ОТ СЛОЖНОГО К ПРОСТОМУ</div>
      {ranked.map((question, i) => <HBar key={question.number} label={`${question.number}. ${question.label}`} value={question.pct} max={100} color={COLORS[i % COLORS.length]} hint={question.attempts ? `${question.pct.toFixed(0)}% · n=${question.attempts} · ${fmtSecs(question.avg_ms)}` : 'нет данных'} />)}
    </div>

    <p className="muted dash-note">В рассылке: {data.eligible} · дублей по телефону: {data.dup_phones} · по студбилету: {data.dup_student_ids}</p>
    <button className="primary w-full" onClick={load}><RotateCcw size={18} />Обновить</button>
  </section>;
}

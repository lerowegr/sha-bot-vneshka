import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Dices, RotateCcw, Trophy } from 'lucide-react';
import { fetchOverview, runRaffle, saveAllowlist, type AllowlistOutcome, type Overview, type Winner } from '../lib/api';

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
  const [count, setCount] = useState(1);
  const [winners, setWinners] = useState<Winner[] | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [drawFailed, setDrawFailed] = useState(false);
  const [onlyListed, setOnlyListed] = useState(false);
  const [allowText, setAllowText] = useState('');
  const [allowInfo, setAllowInfo] = useState<AllowlistOutcome | null>(null);
  const [savingAllow, setSavingAllow] = useState(false);
  const load = useCallback(() => {
    setFailed(false);
    void fetchOverview().then(result => {
      if (result) setData(result);
      else setFailed(true);
    });
  }, []);
  useEffect(load, [load]);
  const draw = useCallback(() => {
    setDrawing(true);
    setDrawFailed(false);
    void runRaffle(count, onlyListed).then(outcome => {
      setDrawing(false);
      if (outcome) {
        setWinners(outcome.winners);
        load();
      } else setDrawFailed(true);
    });
  }, [count, onlyListed, load]);
  const saveList = useCallback(() => {
    setSavingAllow(true);
    void saveAllowlist(allowText).then(outcome => {
      setSavingAllow(false);
      if (outcome) {
        setAllowInfo(outcome);
        setAllowText('');
        load();
      } else setAllowInfo({ added: 0, rejected: [], total: -1, eligible: 0 });
    });
  }, [allowText, load]);

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

    <div className="dash-block">
      <div className="eyebrow">РОЗЫГРЫШ</div>
      <p className="muted">Случайный выбор среди участников (крипторандом, без повторов внутри тиража). Каждый тираж записывается в историю ниже.</p>
      <button type="button" className={`toggle-row ${onlyListed ? 'active' : ''}`} onClick={() => setOnlyListed(value => !value)} aria-pressed={onlyListed}>
        <span className="toggle" />Только комментаторы {data.allowlist.length > 0 ? `(в списке: ${data.allowlist.length})` : '(список пуст)'}
      </button>
      <div className="raffle-controls">
        {[1, 2, 3, 5].map(n => <button key={n} type="button" className={`raffle-count ${n === count ? 'active' : ''}`} onClick={() => setCount(n)}>{n}</button>)}
        <button type="button" className="primary raffle-go" disabled={drawing || !data.total} onClick={draw}><Dices size={18} />{drawing ? 'Крутим…' : 'Выбрать'}</button>
      </div>
      {drawFailed && <p className="form-error" role="alert">Не вышло. Обнови дашборд и попробуй снова.</p>}
      {winners && <div className="winners">
        {winners.map(winner => <div className="winner-card" key={winner.telegram_user_id}>
          <Trophy size={20} />
          <div><strong>{[winner.last_name, winner.first_name].filter(Boolean).join(' ') || 'Без имени'}</strong>
          <span>{[winner.faculty, winner.student_id].filter(Boolean).join(' · ')}{winner.result ? ` · ${winner.result.split('_')[1]}/10` : ''}</span>
          <span className="winner-phone">{winner.phone ?? ''}</span></div>
        </div>)}
      </div>}
      {data.raffles.length > 0 && <div className="raffle-history">
        <div className="eyebrow">ИСТОРИЯ ТИРАЖЕЙ</div>
        {data.raffles.map(draw => <p key={draw.id} className="muted">#{draw.id}{draw.filtered ? ' · по списку' : ''} · {draw.winners.map(w => [w.last_name, w.first_name].filter(Boolean).join(' ') || w.telegram_user_id).join(', ')}</p>)}
      </div>}
    </div>

    <div className="dash-block">
      <div className="eyebrow">СПИСОК КОММЕНТАТОРОВ</div>
      <p className="muted">Вставь ники (с @ или без) или Telegram ID из комментариев под постом — через запятую, пробелы или с новой строки. Список заменяется целиком. Совпадение по нику нечувствительно к регистру.</p>
      <label className="form-field"><span>Ники и ID</span>
        <textarea value={allowText} onChange={event => setAllowText(event.target.value)} rows={3} placeholder="@nick1, @nick2, 123456789" />
      </label>
      <button type="button" className="primary w-full form-submit" disabled={savingAllow} onClick={saveList}>{savingAllow ? 'Сохраняем…' : 'Сохранить список'}</button>
      {allowInfo && (allowInfo.total < 0
        ? <p className="form-error" role="alert">Не сохранилось. Обнови дашборд и попробуй снова.</p>
        : <p className="muted">Добавлено: {allowInfo.added} · всего в списке: {allowInfo.total} · из них прошли тест: {allowInfo.eligible}{allowInfo.rejected.length > 0 ? ` · не распознано: ${allowInfo.rejected.join(', ')}` : ''}</p>)}
    </div>

    <p className="muted dash-note">В рассылке: {data.eligible} · дублей по телефону: {data.dup_phones} · по студбилету: {data.dup_student_ids}</p>
    <button className="primary w-full" onClick={load}><RotateCcw size={18} />Обновить</button>
  </section>;
}

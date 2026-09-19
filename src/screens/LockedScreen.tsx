import { ArrowRight } from 'lucide-react';
import { motion } from 'motion/react';
import { TOTAL_QUESTIONS } from '../data/questions';
import { copy } from '../data/copy';
import { Mascot } from '../components/Mascot';
export function LockedScreen({ score, onNext }: { score: number | null; onNext: () => void }) {
  return <section className="result-screen"><div className="result-intro"><div className="eyebrow"><span className="status-dot" />{copy.locked.eyebrow}</div><Mascot mood="cheer" /><motion.div className="result-code" aria-hidden="true" initial={{ scale: .8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: .5 }}>{score ?? '–'}/{TOTAL_QUESTIONS}</motion.div><h2 className="result-title" data-screen-heading tabIndex={-1}>{copy.locked.title}</h2><p className="result-description">{copy.locked.description}</p></div><div className="result-details"><div className="stats-panel"><div className="eyebrow">{copy.result.stats}</div><p className="muted">Отправь скрин с баллами в комментарии к конкурсному посту — так ты участвуешь в розыгрыше Telegram Premium на 3 месяца.</p></div><button className="primary w-full" onClick={onNext}>{copy.locked.button}<ArrowRight /></button></div></section>;
}

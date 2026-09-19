import { ArrowUpRight, BarChart3, Clock3, Sparkles } from 'lucide-react';
import { motion } from 'motion/react';
import { copy } from '../data/copy';
import { Mascot } from '../components/Mascot';

export function StartScreen({ onStart, onAdmin }: { onStart: () => void; onAdmin?: () => void }) {
  return <section className="start-screen">
    <div className="hero-grid">
      <div className="intro">
        <div className="eyebrow"><span className="status-dot" /> {copy.start.eyebrow}</div>
        <h1 data-screen-heading tabIndex={-1}>Школа<br />Актива <span className="it-word">2026<svg viewBox="0 0 240 26" aria-hidden="true"><path d="M5 18Q100 0 232 12M18 24Q106 10 211 19" /></svg></span><span className="question-mark">?</span></h1>
        <p className="lead">Привет! На связи организаторы Школы Актива 2026.</p>
        <p className="lead">Проходи тест и узнай, как хорошо ты знаком с проектом.</p>
        <div className="start-meta"><span><Clock3 size={16} />{copy.start.time}</span><span className="meta-dot" /><span>10 вопросов</span></div>
      </div>
      <div className="hero-art">
        <div className="orbit-line" aria-hidden="true" />
        <div className="speech-bubble" aria-hidden="true">из искры —<br />пламя!</div>
        <span className="code-sticker" aria-hidden="true">ША 2026<span className="terminal-cursor">_</span></span>
        <Mascot />
      </div>
    </div>
    <div className="quiz-strip"><span><Sparkles size={19} />10 вопросов</span><span className="strip-dash" /><span>Конкурс: Premium на 3 месяца</span><span className="strip-dash" /><span>Отправь результат в комментарии<ArrowUpRight size={18} /></span></div>
    <motion.div className="start-cta-block" initial={{ opacity: 0, y: 24, rotateX: 8 }} whileInView={{ opacity: 1, y: 0, rotateX: 0 }} viewport={{ once: true, amount: .45 }} transition={{ duration: .45 }}>
      <span className="section-number">КАК УЧАСТВОВАТЬ</span>
      <h2>Пройди тест<br />и забери шанс на победу</h2>
      <p className="cta-description">1. Подпишись на ША ВК и ТГ.<br />2. Пройди задание в боте ША.<br />3. Отправь результат (скрин с баллами) в комментарии.<br /><br />Победителя выберем завтра рандомайзером. Подходи сегодня на ФЕСТАРТе на точку Школы Актива за другими интерактивами!</p>
      <motion.button className="primary start-button" whileTap={{ scale: .96, rotateX: 5 }} onClick={onStart}>{copy.start.button}<span className="button-icon"><ArrowUpRight size={25} /></span></motion.button>
      <div className="start-meta cta-meta"><span><Clock3 size={16} />{copy.start.time}</span><span className="meta-dot" /><span>Результат сразу</span></div>
      <p className="start-hint"><span className="handwritten">P. S.</span>{copy.start.hint}</p>
      {onAdmin && <button className="primary admin-button" onClick={onAdmin}><BarChart3 size={20} />Дашборд конкурса<span className="button-icon"><ArrowUpRight size={22} /></span></button>}
    </motion.div>
  </section>;
}

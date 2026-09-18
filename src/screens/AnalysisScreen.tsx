import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Mascot } from '../components/Mascot';
import { copy } from '../data/copy';
export function AnalysisScreen({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  useEffect(() => { const interval = window.setInterval(() => setStep(value => Math.min(value + 1, 5)), 340); const timeout = window.setTimeout(onComplete, 2200); return () => { window.clearInterval(interval); window.clearTimeout(timeout); }; }, [onComplete]);
  const found = step === 5;
  return <section className="analysis-screen" aria-live="polite"><div className={`analysis-mascot ${found ? 'found' : ''}`}><Mascot compact mood="cheer" /></div><div className="eyebrow justify-center">{found ? copy.analysis.match : copy.visual.processing}</div><h2 data-screen-heading tabIndex={-1}>{found ? copy.analysis.match : copy.analysis.title}</h2><div className="analysis-line"><AnimatePresence mode="wait"><motion.p key={step} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}>{found ? copy.visual.done : copy.analysis.lines[step]}</motion.p></AnimatePresence></div><div className="analysis-track"><motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 1.7, ease: 'easeInOut' }} /></div></section>;
}

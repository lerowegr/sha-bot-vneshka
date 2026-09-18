import { motion } from 'motion/react';
import { copy } from '../data/copy';
export function ProgressBar({ current, total }: { current: number; total: number }) {
  return <div className="progress-track" role="progressbar" aria-label={copy.progress} aria-valuemin={0} aria-valuemax={total} aria-valuenow={current}>{Array.from({ length: total }, (_, i) => <div key={i} className="progress-segment"><motion.div initial={false} animate={{ scaleX: i < current ? 1 : 0 }} transition={{ duration: .35 }} /></div>)}</div>;
}

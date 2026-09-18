import { motion } from 'motion/react';
export function StatBar({ label, value, index }: { label: string; value: number; index: number }) {
  return <div className="stat"><div className="stat-label"><span>{label}</span><span className="tabular-nums">{value}<small>/100</small></span></div><div className="stat-track"><motion.div initial={{ scaleX: 0 }} animate={{ scaleX: value / 100 }} transition={{ duration: .8, delay: .25 + index * .12, ease: 'easeOut' }} /></div></div>;
}

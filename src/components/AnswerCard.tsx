import { Check, ArrowUpRight } from 'lucide-react';
import { motion } from 'motion/react';
export function AnswerCard({ text, index, selected, onSelect }: { text: string; index: number; selected: boolean; onSelect: () => void }) {
  return <motion.button type="button" className={`answer-card ${selected ? 'selected' : ''}`} aria-pressed={selected} onClick={onSelect} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .035 }} whileTap={{ scale: .99 }}><span className="answer-index">{selected ? <Check size={17} /> : `0${index + 1}`}</span><span className="answer-text">{text}</span><ArrowUpRight size={18} className="answer-arrow" aria-hidden="true" /></motion.button>;
}

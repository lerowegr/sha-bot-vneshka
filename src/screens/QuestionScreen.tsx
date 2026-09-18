import { ArrowLeft } from 'lucide-react';
import { TOTAL_QUESTIONS, type Question } from '../data/questions';
import { Mascot } from '../components/Mascot';
import { copy } from '../data/copy';
import { ProgressBar } from '../components/ProgressBar';
import { AnswerCard } from '../components/AnswerCard';
export function QuestionScreen({ index, question, selected, onSelect, onBack }: { index: number; question: Question; selected?: number; onSelect: (answerIndex: number) => void; onBack: () => void }) {
  const num = (value: number) => String(value).padStart(2, '0');
  return <section className="question-screen"><div className="question-top"><button className="text-button" onClick={onBack}><ArrowLeft size={16} />{copy.question.back}</button><span className="eyebrow">{copy.question.label} <b className="accent">{num(index + 1)}</b> / {num(TOTAL_QUESTIONS)}</span></div><ProgressBar current={index} total={TOTAL_QUESTIONS} /><div className="question-layout"><div className="question-heading"><span className="big-number" aria-hidden="true">{num(index + 1)}<span>/</span></span><h2 tabIndex={-1} data-screen-heading>{question.title}</h2><p className="muted">Нажми на ответ — сразу перейдём дальше</p><div className="question-companion"><Mascot compact /><span className="handwritten">Правильный ответ узнаешь в конце</span></div></div><div className="answers" role="group" aria-label={question.title}>{question.answers.map((answer, i) => <AnswerCard key={`${answer.text}-${i}`} text={answer.text} index={i} selected={selected === i} onSelect={() => onSelect(i)} />)}</div></div></section>;
}

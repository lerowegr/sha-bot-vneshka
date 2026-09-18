import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from 'motion/react';
import { ArrowUpRight, Asterisk } from 'lucide-react';
import { CommitteeBrand } from './components/CommitteeBrand';
import { StartScreen } from './screens/StartScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { QuestionScreen } from './screens/QuestionScreen';
import { AnalysisScreen } from './screens/AnalysisScreen';
import { ResultScreen } from './screens/ResultScreen';
import { CTScreen } from './screens/CTScreen';
import { copy } from './data/copy';
import { questions, shuffleQuestionAnswers, TOTAL_QUESTIONS, type Question } from './data/questions';
import { calculateScore, toCanonical } from './logic/calculateResult';
import { haptic, setupTelegram, telegram } from './lib/telegram';
import { saveQuiz, type Profile, type SaveStatus } from './lib/api';
import { registerQuizTool } from './lib/webmcp';
type Screen = 'start' | 'profile' | 'question' | 'analysis' | 'result' | 'ct';
export default function App() {
  const [screen, setScreen] = useState<Screen>('start');
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [shuffledQuestions, setShuffledQuestions] = useState(() => shuffleQuestionAnswers(questions));
  const [score, setScore] = useState(0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const saving = useRef(false);
  const navigationLock = useRef(false);
  const answeredIndex = useRef<number | null>(null);
  const questionStart = useRef(0);
  const timesRef = useRef<number[]>([]);
  const submissionRef = useRef<{ answers: number[]; times: number[] } | null>(null);
  const reducedMotion = useReducedMotion();
  useEffect(setupTelegram, []);
  const start = useCallback(() => { answeredIndex.current = null; setAnswers([]); setProfile(null); timesRef.current = []; submissionRef.current = null; setShuffledQuestions(shuffleQuestionAnswers(questions)); setIndex(0); setSaveStatus('idle'); setScreen('profile'); }, []);
  const beginQuiz = useCallback((values: Profile) => { answeredIndex.current = null; setAnswers([]); setProfile(values); timesRef.current = []; submissionRef.current = null; setIndex(0); setSaveStatus('idle'); setScreen('question'); }, []);
  const back = useCallback(() => { if (navigationLock.current) return; navigationLock.current = true; answeredIndex.current = null; if (screen === 'ct') setScreen('result'); if (screen === 'profile') setScreen('start'); if (screen === 'question') { if (index === 0) setScreen('profile'); else setIndex(value => value - 1); } }, [screen, index]);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [screen, index]);
  useEffect(() => { if (screen === 'question') questionStart.current = Date.now(); }, [screen, index]);
  useEffect(() => { const app = telegram(); if (!app?.initData || !app.isVersionAtLeast('6.1')) return; if (screen === 'question' || screen === 'profile' || screen === 'ct') app.BackButton.show(); else app.BackButton.hide(); app.BackButton.onClick(back); return () => { app.BackButton.offClick(back); app.BackButton.hide(); }; }, [screen, back]);
  const persist = useCallback(async (answers: number[], times: number[], values: Profile | null): Promise<SaveStatus> => { if (saving.current) return 'saving'; if (!values) return 'failed'; saving.current = true; setSaveStatus('saving'); try { const outcome = await saveQuiz(answers, times, values); if (outcome.status === 'saved' && typeof outcome.score === 'number') setScore(outcome.score); setSaveStatus(outcome.status); return outcome.status; } finally { saving.current = false; } }, []);
  const completeQuiz = useCallback((completedAnswers: number[], qs: readonly Question[] = shuffledQuestions, values: Profile | null = profile) => { const canonical = toCanonical(completedAnswers, qs); const times = timesRef.current.slice(); submissionRef.current = { answers: canonical, times }; const value = calculateScore(completedAnswers, qs); setAnswers(completedAnswers); setScore(value); setScreen('analysis'); return { score: value, saved: persist(canonical, times, values) }; }, [persist, shuffledQuestions, profile]);
  useEffect(() => registerQuizTool(async (completedAnswers, qs, values, times) => {
    if (saving.current) throw new Error('A result is still being saved');
    if (values) setProfile(values);
    if (times) timesRef.current = [...times];
    let completion!: ReturnType<typeof completeQuiz>;
    flushSync(() => { completion = completeQuiz(completedAnswers, qs ?? shuffledQuestions, values ?? profile); });
    const saved = await completion.saved;
    flushSync(() => setScreen('result'));
    return { score: completion.score, saved };
  }), [completeQuiz, shuffledQuestions, profile]);
  const chooseAnswer = (answerIndex: number) => {
    if (answeredIndex.current === index) return;
    answeredIndex.current = index;
    haptic();
    timesRef.current[index] = Date.now() - questionStart.current;
    const updated = [...answers];
    updated[index] = answerIndex;
    setAnswers(updated);
    if (index < TOTAL_QUESTIONS - 1) setIndex(index + 1);
    else completeQuiz(updated);
  };
  const reveal = useCallback(() => setScreen('result'), []);
  const focusHeading = (definition: unknown) => { if (definition && typeof definition === 'object' && 'opacity' in definition && definition.opacity === 1) { navigationLock.current = false; document.querySelector<HTMLElement>('[data-screen-heading]')?.focus({ preventScroll: true }); } };
  return <MotionConfig reducedMotion="user"><div className="app-shell"><header className="header"><CommitteeBrand /><div className="header-right"><span className="edition">ШКОЛА АКТИВА 2026 <ArrowUpRight size={14} /></span></div></header><main><AnimatePresence mode="wait"><motion.div className="screen-container" key={`${screen}-${screen === 'question' ? index : ''}`} initial={{ opacity: 0, y: reducedMotion ? 0 : 18, rotateX: reducedMotion ? 0 : 3 }} animate={{ opacity: 1, y: 0, rotateX: 0 }} exit={{ opacity: 0, y: reducedMotion ? 0 : -12, rotateX: reducedMotion ? 0 : -2 }} transition={{ duration: .28, ease: [0.22, 1, 0.36, 1] }} onAnimationComplete={focusHeading}>
    {screen === 'start' && <StartScreen onStart={start} />}
    {screen === 'profile' && <ProfileScreen onSubmit={beginQuiz} onBack={back} />}
    {screen === 'question' && <QuestionScreen index={index} question={shuffledQuestions[index]} selected={answers[index]} onSelect={chooseAnswer} onBack={back} />}
    {screen === 'analysis' && <AnalysisScreen onComplete={reveal} />}
    {screen === 'result' && <ResultScreen score={score} onNext={() => setScreen('ct')} onRestart={start} saveStatus={saveStatus} onSave={() => { const sub = submissionRef.current; void persist(sub?.answers ?? [], sub?.times ?? [], profile); }} />}
    {screen === 'ct' && <CTScreen onBack={back} />}
  </motion.div></AnimatePresence></main><footer><span>{copy.footer}<Asterisk className="footer-dot" size={17} aria-hidden="true" /></span><span>Школа Актива 2026</span></footer></div></MotionConfig>;
}

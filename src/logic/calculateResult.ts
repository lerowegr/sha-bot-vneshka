import { TOTAL_QUESTIONS, type Question } from '../data/questions';
export const RESULT_IDS = Array.from({ length: TOTAL_QUESTIONS + 1 }, (_, score) => `score_${score}`);
export function scoreToResultId(score: number): string {
  if (!Number.isInteger(score) || score < 0 || score > TOTAL_QUESTIONS) throw new Error(`Expected score 0..${TOTAL_QUESTIONS}`);
  return `score_${score}`;
}
export function calculateScore(selected: readonly number[], shuffled: readonly Question[]): number {
  if (selected.length !== TOTAL_QUESTIONS || shuffled.length !== TOTAL_QUESTIONS) throw new Error(`Expected exactly ${TOTAL_QUESTIONS} answers`);
  let score = 0;
  selected.forEach((answerIndex, q) => {
    const answers = shuffled[q]?.answers;
    if (!answers || !Number.isInteger(answerIndex) || answerIndex < 0 || answerIndex >= answers.length) throw new Error('Invalid answer index');
    if (answers[answerIndex].correct) score++;
  });
  return score;
}
// Back-compat name used by App: returns result id like score_7.
export function calculateResult(selected: readonly number[], shuffled: readonly Question[]): string {
  return scoreToResultId(calculateScore(selected, shuffled));
}
export function scoreMessage(score: number): string {
  if (score >= 9) return 'Легенда ША! Ты знаешь проект почти идеально.';
  if (score >= 7) return 'Очень круто! Ты явно свой человек.';
  if (score >= 5) return 'Неплохо! Кое-что уже знаешь, остальное узнаешь на ША.';
  if (score >= 3) return 'Начало положено! ША тебя точно удивит.';
  return 'Спасибо за прохождение! Теперь ты знаешь про ША немного больше.';
}

import { describe, expect, it } from 'vitest';
import { calculateScore, scoreToResultId } from './calculateResult';
import { questions, shuffleQuestionAnswers, TOTAL_QUESTIONS } from '../data/questions';

describe('quiz scoring', () => {
  it('has ten questions with exactly one correct answer each', () => {
    expect(questions).toHaveLength(TOTAL_QUESTIONS);
    expect(TOTAL_QUESTIONS).toBe(10);
    questions.forEach(question => {
      expect(question.answers.filter(a => a.correct)).toHaveLength(1);
    });
  });
  it('shuffles answer positions without changing correctness or source data', () => {
    const originalOrders = questions.map(question => question.answers.map(answer => answer.text));
    const shuffled = shuffleQuestionAnswers(questions, () => 0);

    shuffled.forEach((question, index) => {
      expect(new Set(question.answers.map(answer => answer.text))).toEqual(new Set(originalOrders[index]));
      expect(question.answers.filter(a => a.correct)).toHaveLength(1);
      question.answers.forEach(answer => {
        expect(questions[index].answers).toContainEqual(answer);
      });
    });
    expect(questions.map(question => question.answers.map(answer => answer.text))).toEqual(originalOrders);
  });
  it('scores 10 when all answers are correct', () => {
    const shuffled = shuffleQuestionAnswers(questions, () => 0.5);
    const selected = shuffled.map(q => q.answers.findIndex(a => a.correct));
    expect(calculateScore(selected, shuffled)).toBe(10);
    expect(scoreToResultId(10)).toBe('score_10');
  });
  it('scores 0 when all answers are wrong', () => {
    const shuffled = shuffleQuestionAnswers(questions);
    const selected = shuffled.map(q => {
      const wrong = q.answers.findIndex(a => !a.correct);
      return wrong;
    });
    expect(calculateScore(selected, shuffled)).toBe(0);
  });
  it('rejects incomplete and invalid answers', () => {
    const shuffled = shuffleQuestionAnswers(questions);
    expect(() => calculateScore([], shuffled)).toThrow();
    expect(() => calculateScore(Array(9).fill(0), shuffled)).toThrow();
    expect(() => calculateScore(Array(10).fill(99), shuffled)).toThrow();
    expect(() => scoreToResultId(11)).toThrow();
    expect(() => scoreToResultId(-1)).toThrow();
  });
});

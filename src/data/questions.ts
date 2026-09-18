export type Answer = { text: string; correct: boolean };
export type Question = { title: string; answers: Answer[] };
type RawAnswer = string | { text: string; correct?: boolean };
const question = (title: string, answers: RawAnswer[], correctIndex: number): Question => ({
  title,
  answers: answers.map((answer, i) => {
    const text = typeof answer === 'string' ? answer : answer.text;
    return { text, correct: i === correctIndex };
  }),
});
export const TOTAL_QUESTIONS = 10;
export const questions: Question[] = [
  question('Сколько лет исполняется проекту в этом году?', ['20', '22', '25', '24'], 2),
  question('Продолжи фразу «Школа Актива…»', ['море знаний, позитива', 'много счастья, позитива', 'море цифр, позитива'], 0),
  question('Где проходит проект Школа Актива?', ['УОК Лесное Озеро', 'УОК Лесная Поляна', 'УОК Лесная Опушка', 'УОК Березовая Роща'], 0),
  question('Какого цвета футболки у Наставников?', ['фиолетовые', 'синие', 'белые', 'красные'], 1),
  question('Сколько дней идёт Школа Актива?', ['1', '2', '3', '4'], 2),
  question('Как зовут Директоров ША в этом году?', ['Катя и Лера', 'Арина и Влад', 'Даша и Кристина', 'Катя и Никита'], 0),
  question('Продолжи фразу «Из искры — …»', ['свет', 'позитив', 'пламя', 'костёр'], 2),
  question('У какого организатора фиолетовая футболка?', ['тренера', 'методиста', 'техпода', 'наставника'], 0),
  question('Когда пройдет проект в этом году?', ['в сентябре', 'в октябре', 'в ноябре', 'в декабре'], 2),
  question('Хочешь на ША?', ['Да', 'Пока думаю', 'Нет('], 0),
];

export function shuffleQuestionAnswers(source: readonly Question[], random: () => number = Math.random): Question[] {
  return source.map(question => {
    const answers = [...question.answers];
    for (let index = answers.length - 1; index > 0; index--) {
      const target = Math.floor(random() * (index + 1));
      [answers[index], answers[target]] = [answers[target], answers[index]];
    }
    return { ...question, answers };
  });
}

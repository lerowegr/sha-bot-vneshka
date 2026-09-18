import { useState } from 'react';
import { ArrowLeft, ArrowUpRight } from 'lucide-react';
import { copy } from '../data/copy';
import type { Profile } from '../lib/api';

const EMPTY: Profile = { last_name: '', first_name: '', middle_name: '', course: '', faculty: '', student_id: '', phone: '' };
const NAME_RE = /^[A-Za-zА-Яа-яЁё\- ]{1,60}$/;
const COURSES = [
  { value: 'b1', label: 'Бакалавриат, 1 курс' }, { value: 'b2', label: 'Бакалавриат, 2 курс' },
  { value: 'b3', label: 'Бакалавриат, 3 курс' }, { value: 'b4', label: 'Бакалавриат, 4 курс' },
  { value: 'm1', label: 'Магистратура, 1 курс' }, { value: 'm2', label: 'Магистратура, 2 курс' },
];
const FACULTIES = ['ИТиАБД', 'ВШУ', 'МЭО', 'СНиМК', 'ФинФак', 'ЮрФак', 'НАБ', 'ФЭБ'];

function validate(values: Profile): Partial<Record<keyof Profile, boolean>> {
  const bad: Partial<Record<keyof Profile, boolean>> = {};
  (['last_name', 'first_name', 'middle_name'] as const).forEach(key => {
    const clean = values[key].trim().replace(/\s+/g, ' ');
    if (!NAME_RE.test(clean)) bad[key] = true;
  });
  if (!COURSES.some(option => option.value === values.course)) bad.course = true;
  if (!FACULTIES.includes(values.faculty)) bad.faculty = true;
  if (!/^[A-Za-zА-Яа-яЁё0-9\-]{4,20}$/.test(values.student_id.trim())) bad.student_id = true;
  const digits = values.phone.replace(/[\s\-()]/g, '');
  if (!/^(\+7|8)\d{10}$/.test(digits) && !/^\d{10}$/.test(digits)) bad.phone = true;
  return bad;
}

export function ProfileScreen({ onSubmit, onBack }: { onSubmit: (profile: Profile) => void; onBack: () => void }) {
  const [values, setValues] = useState<Profile>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof Profile, boolean>>>({});
  const [tried, setTried] = useState(false);
  const set = (key: keyof Profile) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const next = { ...values, [key]: event.target.value };
    setValues(next);
    if (tried) setErrors(validate(next));
  };
  const submit = () => {
    const bad = validate(values);
    setTried(true);
    setErrors(bad);
    if (Object.keys(bad).length > 0) return;
    onSubmit({
      last_name: values.last_name.trim().replace(/\s+/g, ' '),
      first_name: values.first_name.trim().replace(/\s+/g, ' '),
      middle_name: values.middle_name.trim().replace(/\s+/g, ' '),
      course: values.course,
      faculty: values.faculty,
      student_id: values.student_id.trim(),
      phone: values.phone.trim(),
    });
  };
  const field = (key: keyof Profile, label: string, props: object = {}) => (
    <label className={`form-field ${errors[key] ? 'invalid' : ''}`}>
      <span>{label}</span>
      <input value={values[key]} onChange={set(key)} autoComplete="off" {...props} />
    </label>
  );
  return <section className="profile-screen">
    <button className="text-button" onClick={onBack}><ArrowLeft size={16} />{copy.profile.back}</button>
    <div className="eyebrow">{copy.profile.eyebrow}</div>
    <h2 data-screen-heading tabIndex={-1}>{copy.profile.title}</h2>
    <p className="muted">{copy.profile.description}</p>
    <div className="form-grid">
      {field('last_name', copy.profile.lastName, { placeholder: 'Иванова' })}
      {field('first_name', copy.profile.firstName, { placeholder: 'Анна' })}
      {field('middle_name', copy.profile.middleName, { placeholder: 'Сергеевна' })}
      <label className={`form-field ${errors.course ? 'invalid' : ''}`}>
        <span>{copy.profile.course}</span>
        <select value={values.course} onChange={set('course')}>
          <option value="">{copy.profile.coursePlaceholder}</option>
          {COURSES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label className={`form-field ${errors.faculty ? 'invalid' : ''}`}>
        <span>{copy.profile.faculty}</span>
        <select value={values.faculty} onChange={set('faculty')}>
          <option value="">{copy.profile.facultyPlaceholder}</option>
          {FACULTIES.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      {field('student_id', copy.profile.studentId, { placeholder: '123456', inputMode: 'text' })}
      {field('phone', copy.profile.phone, { placeholder: copy.profile.phonePlaceholder, inputMode: 'tel', type: 'tel' })}
    </div>
    {tried && Object.keys(errors).length > 0 && <p className="form-error" role="alert">{copy.profile.errors}</p>}
    <button className="primary w-full form-submit" onClick={submit}>{copy.profile.button}<ArrowUpRight size={22} /></button>
  </section>;
}

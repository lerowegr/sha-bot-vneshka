import { useState } from 'react';

/** Логотип Школы Актива в шапке. Файл: public/brand-sha/flower-black.png */
export function CommitteeBrand() {
  const [missing, setMissing] = useState(false);
  return <div className="brand">
    <span className={`committee-logo ${missing ? 'is-placeholder' : ''}`}>
      {!missing ? <img src="/brand-sha/flower-black.png" alt="Логотип Школы Актива" onError={() => setMissing(true)} /> : <span aria-label="Место для логотипа Школы Актива">ША<span className="logo-corner" /></span>}
    </span>
    <span className="brand-text"><strong>Школа<br />Актива</strong><span>тест • 2026</span></span>
  </div>;
}

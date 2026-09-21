import { useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import type { Winner } from '../lib/api';

const COLORS = ['#2CE719', '#BF2AFF', '#FF8512', '#1C63FF', '#FFCC00', '#F70302', '#ffffff'];

function ConfettiCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf = 0;
    let dead = false;
    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener('resize', resize);
    type Piece = { x: number; y: number; vx: number; vy: number; size: number; color: string; rot: number; vr: number; round: boolean };
    const pieces: Piece[] = Array.from({ length: 160 }, () => ({
      x: Math.random() * canvas.width, y: -20 - Math.random() * canvas.height * 0.5,
      vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3,
      size: 5 + Math.random() * 7, color: COLORS[(Math.random() * COLORS.length) | 0],
      rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.2, round: Math.random() < 0.5,
    }));
    const start = performance.now();
    const tick = (now: number) => {
      if (dead) return;
      const elapsed = now - start;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = elapsed > 2800 ? Math.max(0, 1 - (elapsed - 2800) / 900) : 1;
      for (const p of pieces) {
        p.x += p.vx + Math.sin(now * 0.002 + p.y * 0.01);
        p.y += p.vy;
        p.rot += p.vr;
        if (p.y > canvas.height + 20) { p.y = -20; p.x = Math.random() * canvas.width; }
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        if (p.round) { ctx.beginPath(); ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2); ctx.fill(); }
        else ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }
      ctx.globalAlpha = 1;
      if (elapsed < 3700) raf = requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
    raf = requestAnimationFrame(tick);
    return () => { dead = true; cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, []);
  return <canvas ref={ref} className="confetti-canvas" aria-hidden="true" />;
}

function winnerLine(winner: Winner): React.ReactNode {
  const fio = [winner.last_name, winner.first_name, winner.middle_name].filter(Boolean).join(' ') || 'Победитель';
  const contact = winner.telegram_username ? `username @${winner.telegram_username}` : winner.phone;
  return <>
    Поздравляем, <strong>{fio}</strong>{winner.faculty ? <> с факультета «{winner.faculty}»</> : null} выиграла!
    <br />Для связи используйте {contact ? <strong>{contact}</strong> : 'контакты из анкеты'}.
  </>;
}

export function CongratsOverlay({ winners, onClose }: { winners: Winner[]; onClose: () => void }) {
  return <div className="congrats-overlay" role="dialog" aria-label="Поздравляем победителей">
    <ConfettiCanvas />
    <motion.div className="congrats-card" initial={{ scale: .85, opacity: 0, rotate: -2 }} animate={{ scale: 1, opacity: 1, rotate: 0 }} transition={{ duration: .4, ease: [0.22, 1, 0.36, 1] }}>
      <motion.h2 initial={{ scale: .7 }} animate={{ scale: 1 }} transition={{ delay: .15, type: 'spring', stiffness: 260, damping: 14 }}>Поздравляем!</motion.h2>
      {winners.map(winner => <p className="congrats-line" key={winner.telegram_user_id}>{winnerLine(winner)}</p>)}
      <button type="button" className="primary w-full" onClick={onClose}>Отлично</button>
    </motion.div>
  </div>;
}

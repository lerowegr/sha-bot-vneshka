import { useRef } from 'react';
import { motion, useMotionValue, useSpring, useReducedMotion } from 'motion/react';

const ART = {
  hero: '/brand-sha/flower-purple.png',
  friend: '/brand-sha/blob-green.png',
  cheer: '/brand-sha/flower-yellow.png',
} as const;

export type MascotMood = keyof typeof ART;

/** Цветок — маскот Школы Актива 2026 (ассеты из public/brand-sha). */
export function Mascot({ compact = false, mood }: { compact?: boolean; mood?: MascotMood }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rawTiltX = useMotionValue(0);
  const rawTiltY = useMotionValue(0);
  const tiltX = useSpring(rawTiltX, { stiffness: 110, damping: 15 });
  const tiltY = useSpring(rawTiltY, { stiffness: 110, damping: 15 });
  const src = ART[mood ?? (compact ? 'friend' : 'hero')];
  return <motion.div ref={ref} className={`mascot ${compact ? 'mascot-compact' : ''}`} style={{ rotateX: tiltX, rotateY: tiltY }} onPointerMove={event => {
    if (reduced) return;
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const px = (event.clientX - box.left) / box.width - .5;
    const py = (event.clientY - box.top) / box.height - .5;
    x.set(px * 12); y.set(py * 9); rawTiltY.set(px * 7); rawTiltX.set(py * -5);
  }} onPointerLeave={() => { x.set(0); y.set(0); rawTiltX.set(0); rawTiltY.set(0); }}>
    <img src={src} alt="Цветок — маскот Школы Актива" className="mascot-bob" draggable={false} />
  </motion.div>;
}

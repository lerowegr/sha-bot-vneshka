import { useRef } from 'react';
import { motion, useMotionValue, useSpring, useReducedMotion } from 'motion/react';

/** Author-drawn penguin mascot for Школа Актива 2026. */
export function Mascot({ compact = false }: { compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rawTiltX = useMotionValue(0);
  const rawTiltY = useMotionValue(0);
  const eyeX = useSpring(x, { stiffness: 180, damping: 18 });
  const eyeY = useSpring(y, { stiffness: 180, damping: 18 });
  const tiltX = useSpring(rawTiltX, { stiffness: 110, damping: 15 });
  const tiltY = useSpring(rawTiltY, { stiffness: 110, damping: 15 });
  return <motion.div ref={ref} className={`mascot ${compact ? 'mascot-compact' : ''}`} style={{ rotateX: tiltX, rotateY: tiltY }} onPointerMove={event => {
    if (reduced) return;
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const px = (event.clientX - box.left) / box.width - .5;
    const py = (event.clientY - box.top) / box.height - .5;
    x.set(px * 12); y.set(py * 9); rawTiltY.set(px * 7); rawTiltX.set(py * -5);
  }} onPointerLeave={() => { x.set(0); y.set(0); rawTiltX.set(0); rawTiltY.set(0); }}>
    <svg viewBox="0 0 560 480" fill="none" role="img" aria-label="Весёлый мультяшный пингвин — маскот Школы Актива">
      <defs>
        <linearGradient id="penguin-black" x1="190" y1="92" x2="372" y2="390" gradientUnits="userSpaceOnUse"><stop stopColor="#3B3A43"/><stop offset="1" stopColor="#17171A"/></linearGradient>
        <linearGradient id="penguin-white" x1="244" y1="170" x2="294" y2="375" gradientUnits="userSpaceOnUse"><stop stopColor="#FFFDF8"/><stop offset="1" stopColor="#EDE8DC"/></linearGradient>
        <linearGradient id="hoodie" x1="203" y1="261" x2="346" y2="350" gradientUnits="userSpaceOnUse"><stop stopColor="#C9B8F2"/><stop offset="1" stopColor="#9783D2"/></linearGradient>
      </defs>
      <ellipse className="mascot-shadow" cx="283" cy="433" rx="135" ry="18" fill="#24231F" opacity=".16"/>
      <g className="mascot-body" stroke="#24231F" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M204 388C195 402 172 405 151 413C136 419 139 436 157 437L231 434C243 433 246 420 237 414L219 391Z" fill="#F2A93B"/>
        <path d="M342 388C354 402 376 405 398 413C414 419 411 436 393 437L318 434C306 433 303 420 312 414L328 391Z" fill="#F2A93B"/>
        <path d="M216 419L181 425M329 419L365 425" stroke="#C66B28" strokeWidth="3"/>
        <path d="M179 247C130 257 111 299 90 286C67 272 99 228 127 218C146 211 164 217 181 226Z" fill="#242329"/>
        <g className="mascot-hand"><path d="M377 227C417 220 432 184 439 153C441 143 454 145 454 156C459 139 468 135 474 141C480 147 469 161 469 166C481 153 491 156 491 165C492 174 474 192 460 201C442 213 426 243 386 258Z" fill="#242329"/></g>
        <path d="M174 213C177 137 219 82 282 80C348 78 390 138 391 222L384 317C378 376 340 405 282 406C222 406 180 375 173 318Z" fill="url(#penguin-black)"/>
        <path d="M194 154C217 114 247 99 281 101C316 102 349 121 369 158C345 145 326 151 309 172C294 190 268 189 253 171C237 151 217 146 194 154Z" fill="#F9F6EC"/>
        <path d="M203 211C210 163 240 143 281 143C323 143 355 168 361 218L353 316C349 360 322 383 282 384C240 384 212 359 207 317Z" fill="url(#penguin-white)"/>
        <path d="M202 269C226 251 251 248 280 249C310 249 337 255 360 274L355 329C337 347 313 354 282 354C250 354 226 347 205 328Z" fill="url(#hoodie)"/>
        <path d="M205 287C244 300 319 299 358 287M239 269L224 310M324 268L340 309" stroke="#7661B3" strokeWidth="3"/>
        <path d="M264 292L277 303L298 279" stroke="#FFFDF8" strokeWidth="7"/>
        <g className="mascot-eyes" stroke="none"><motion.g style={{ x: eyeX, y: eyeY }}><ellipse cx="247" cy="194" rx="12" ry="18" fill="#24231F"/><ellipse cx="317" cy="194" rx="12" ry="18" fill="#24231F"/><circle cx="251" cy="188" r="3.5" fill="white"/><circle cx="321" cy="188" r="3.5" fill="white"/></motion.g></g>
        <path d="M262 220L282 207L303 220L282 235Z" fill="#F2A93B"/>
        <path d="M263 220H302" stroke="#C66B28" strokeWidth="2.5"/>
        <path d="M218 231L230 233M334 233L347 231" stroke="#EF765E" strokeWidth="7"/>
        <path d="M190 179L176 169M372 177L387 165" strokeWidth="3"/>
      </g>
      <g className="mascot-floaters" stroke="#24231F" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M93 345L101 361L118 363L105 374L108 391L93 383L78 391L81 374L68 363L85 361Z" fill="#F4BC41"/>
        <path d="M447 286V314M433 300H461M115 149L98 143M124 128L115 113M417 105L426 88M439 121L457 112"/>
        <path d="M388 347C414 338 433 343 444 360" strokeDasharray="7 8"/>
      </g>
    </svg>
  </motion.div>;
}

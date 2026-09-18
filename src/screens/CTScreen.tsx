import { ArrowLeft, ArrowUpRight } from 'lucide-react';
import { motion } from 'motion/react';
import { copy } from '../data/copy';
import { channelUrl, telegram } from '../lib/telegram';
export function CTScreen({ onBack }: { onBack: () => void }) {
  const url = channelUrl();
  return <section className="ct-screen"><button className="text-button" onClick={onBack}><ArrowLeft size={16} />{copy.ct.back}</button><div className="ct-content"><motion.img src="/brand-sha/logo-sha-2026.png" alt="Школа Актива 2026" className="ct-logo" loading="lazy" initial={{ scale: .85, opacity: 0, rotate: -6 }} animate={{ scale: 1, opacity: 1, rotate: 0 }} transition={{ duration: .45, ease: [0.22, 1, 0.36, 1] }} /><div className="eyebrow justify-center">{copy.ct.eyebrow}</div><h2 data-screen-heading tabIndex={-1}>{copy.visual.ctLine}<br />{copy.visual.ctPrefix}<span className="accent">{copy.visual.ctAccent}</span></h2><p className="ct-intro">{copy.ct.intro}</p><p className="muted">{copy.ct.description}</p><p className="muted">{copy.ct.news}</p>{url ? <motion.a className="primary" href={url} target="_blank" rel="noopener noreferrer" whileHover={{ y: -2 }} whileTap={{ scale: .98 }} onClick={event => { const app = telegram(); if (app?.initData) { event.preventDefault(); app.openTelegramLink(url); } }}>{copy.ct.button}<ArrowUpRight size={22} /></motion.a> : <><button className="primary w-full" disabled>{copy.ct.button}<ArrowUpRight size={22} /></button><p className="channel-soon">{copy.ct.soon}</p></>}<p className="goodbye">{copy.ct.goodbye}</p></div></section>;
}

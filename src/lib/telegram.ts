type BackButton = { show(): void; hide(): void; onClick(fn: () => void): void; offClick(fn: () => void): void };
type WebApp = {
  initData: string; viewportStableHeight: number;
  ready(): void; expand(): void; isVersionAtLeast(version: string): boolean;
  setHeaderColor(color: string): void; setBackgroundColor(color: string): void;
  openTelegramLink(url: string): void;
  onEvent(event: string, fn: () => void): void; offEvent(event: string, fn: () => void): void;
  BackButton: BackButton;
  HapticFeedback?: { selectionChanged(): void; notificationOccurred(type: 'success'): void };
};
declare global { interface Window { Telegram?: { WebApp: WebApp } } }
export const telegram = () => window.Telegram?.WebApp;
export const initData = () => telegram()?.initData ?? '';
export function haptic() {
  const app = telegram();
  if (app?.initData && app.isVersionAtLeast('6.1')) app.HapticFeedback?.selectionChanged();
}
export function setupTelegram(): () => void {
  const app = telegram();
  if (!app) return () => {};
  app.ready(); app.expand();
  if (app.initData && app.isVersionAtLeast('6.1')) { app.setHeaderColor('#F7F4EB'); app.setBackgroundColor('#F7F4EB'); }
  const update = () => { if (app.initData && app.viewportStableHeight > 0) document.documentElement.style.setProperty('--app-height', `${app.viewportStableHeight}px`); };
  update(); app.onEvent('viewportChanged', update);
  return () => { app.offEvent('viewportChanged', update); document.documentElement.style.removeProperty('--app-height'); };
}
export function channelUrl(): string | null {
  const value = import.meta.env.VITE_TELEGRAM_CHANNEL_URL?.trim();
  if (!value) return null;
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 't.me' && url.pathname.length > 1 && !url.username && !url.password ? url.href : null; } catch { return null; }
}

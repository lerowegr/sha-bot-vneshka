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
  if (app.initData && app.isVersionAtLeast('6.1')) { app.setHeaderColor('#F5F1E6'); app.setBackgroundColor('#F5F1E6'); }
  const update = () => { if (app.initData && app.viewportStableHeight > 0) document.documentElement.style.setProperty('--app-height', `${app.viewportStableHeight}px`); };
  update(); app.onEvent('viewportChanged', update);
  return () => { app.offEvent('viewportChanged', update); document.documentElement.style.removeProperty('--app-height'); };
}

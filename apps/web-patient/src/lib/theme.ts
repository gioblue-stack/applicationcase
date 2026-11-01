// Темы-пингвины: палитра сайта следует за цветом пингвина. Цвета — в globals.css ([data-theme=…]),
// здесь только список, сохранение на устройстве и применение к <html>.

export type ThemeId = "blue" | "pink" | "sage" | "lavender" | "sand";
export type Mode = "system" | "light" | "dark";

/** primary — цвет панели браузера (meta theme-color) в светлом режиме. */
export const THEMES: { id: ThemeId; name: string; primary: string }[] = [
  { id: "blue", name: "Синий", primary: "#2F6FA8" },
  { id: "pink", name: "Розовый", primary: "#B8466E" },
  { id: "sage", name: "Шалфей", primary: "#3F7D63" },
  { id: "lavender", name: "Лаванда", primary: "#6B5BA8" },
  { id: "sand", name: "Песочный", primary: "#9A6A3A" },
];

export const MODES: { id: Mode; name: string }[] = [
  { id: "system", name: "Как в телефоне" },
  { id: "light", name: "Светлое" },
  { id: "dark", name: "Тёмное" },
];

const THEME_KEY = "mc_theme";
const MODE_KEY = "mc_mode";
const DARK_BAR = "#12161B";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

export function isTheme(value: string | null): value is ThemeId {
  return THEMES.some((t) => t.id === value);
}

/** Выбрана ли тема на этом устройстве — при первом входе показываем экран «Выбери тему». */
export function themeChosen(): boolean {
  return isTheme(read(THEME_KEY));
}

export function currentTheme(): ThemeId {
  const saved = read(THEME_KEY);
  return isTheme(saved) ? saved : "blue";
}

export function currentMode(): Mode {
  const saved = read(MODE_KEY);
  return saved === "light" || saved === "dark" ? saved : "system";
}

function isDark(mode: Mode) {
  return mode === "dark" || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

/** Применить без сохранения (предпросмотр на экране выбора) или с сохранением. */
export function applyTheme(theme: ThemeId, mode: Mode = currentMode(), { save = true } = {}) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.mode = mode;
  const meta = document.querySelector('meta[name="theme-color"]');
  meta?.setAttribute("content", isDark(mode) ? DARK_BAR : THEMES.find((t) => t.id === theme)!.primary);
  if (save) {
    write(THEME_KEY, theme);
    write(MODE_KEY, mode);
  }
}

/** Выполняется в <head> до отрисовки — без вспышки синей темы у тех, кто выбрал другую. */
export const THEME_BOOT_SCRIPT = `(function(){try{
var t=localStorage.getItem("${THEME_KEY}"),m=localStorage.getItem("${MODE_KEY}"),r=document.documentElement;
var ok=${JSON.stringify(THEMES.map((t) => t.id))};
if(ok.indexOf(t)>=0)r.dataset.theme=t;r.dataset.mode=(m==="light"||m==="dark")?m:"system";
}catch(e){}})();`;

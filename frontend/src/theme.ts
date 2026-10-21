// Theme handling. The stored choice wins; without one the OS preference
// (prefers-color-scheme) decides. index.html applies the same resolution in an
// inline script before first paint, so this module only has to keep the two
// in sync afterwards.

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'ai-tutor-theme';

const LIGHT_QUERY = '(prefers-color-scheme: light)';

export function systemTheme(): Theme {
  return window.matchMedia(LIGHT_QUERY).matches ? 'light' : 'dark';
}

export function storedTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : null;
  } catch {
    // localStorage can be unavailable (private mode, blocked cookies).
    return null;
  }
}

export function resolveInitialTheme(): Theme {
  return storedTheme() ?? systemTheme();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
}

export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Persisting the choice is best effort.
  }
}

/** Call `onChange` whenever the OS theme changes, until the returned disposer. */
export function watchSystemTheme(onChange: (theme: Theme) => void): () => void {
  const media = window.matchMedia(LIGHT_QUERY);
  const listener = (event: MediaQueryListEvent) => {
    onChange(event.matches ? 'light' : 'dark');
  };
  media.addEventListener('change', listener);
  return () => media.removeEventListener('change', listener);
}

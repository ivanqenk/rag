// Tema claro u oscuro elegido por el usuario. Claro por defecto; la elección se recuerda en
// este navegador (localStorage puede no estar disponible: modo privado, cookies bloqueadas).

import { useState } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'tema'

export function storedTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/** Aplica el tema al documento (los colores están en index.css bajo [data-theme]). */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(storedTheme)
  function setTheme(next: Theme) {
    applyTheme(next)
    setThemeState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Sin almacenamiento el tema dura hasta recargar la página.
    }
  }
  return [theme, setTheme]
}

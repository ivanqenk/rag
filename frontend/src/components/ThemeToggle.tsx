import { useTheme, type Theme } from '../theme'

// Texto en lugar de emojis: los emojis dependen de las fuentes del sistema y en algunos
// equipos se ven como un cuadro vacío.
const OPTIONS: Array<{ value: Theme; label: string; text: string }> = [
  { value: 'light', label: 'Tema claro', text: 'Claro' },
  { value: 'dark', label: 'Tema oscuro', text: 'Oscuro' },
]

/** Selector Claro / Oscuro (dos botones con aria-pressed). */
export function ThemeToggle() {
  const [theme, setTheme] = useTheme()
  return (
    <div className="theme-toggle" role="group" aria-label="Tema">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-label={option.label}
          title={option.label}
          aria-pressed={theme === option.value}
          onClick={() => setTheme(option.value)}
        >
          {option.text}
        </button>
      ))}
    </div>
  )
}

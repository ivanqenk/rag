import { useTheme, type Theme } from '../theme'
import { Icon, type IconName } from './Icon'

// Iconos SVG propios en lugar de emojis: los emojis dependen de las fuentes del sistema y
// en algunos equipos se ven como un cuadro vacío. En el móvil solo se ve el icono.
const OPTIONS: Array<{ value: Theme; label: string; text: string; icon: IconName }> = [
  { value: 'light', label: 'Tema claro', text: 'Claro', icon: 'sun' },
  { value: 'dark', label: 'Tema oscuro', text: 'Oscuro', icon: 'moon' },
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
          <Icon name={option.icon} size={16} />
          <span className="theme-label">{option.text}</span>
        </button>
      ))}
    </div>
  )
}

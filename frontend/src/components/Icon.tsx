// Iconos SVG propios (trazos simples de 24×24). Van dentro de la app: no dependen de fuentes
// del sistema ni de dominios externos (la CSP solo permite recursos propios). Son decorativos:
// el texto que los acompaña es lo que leen los lectores de pantalla.

const PATHS = {
  library: [
    'M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z',
    'M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z',
  ],
  ask: [
    'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    'M9 9.5a3 3 0 0 1 5.6 1.5c0 2-3 2-3 3.5',
    'M12 15.5h.01',
  ],
  trash: ['M3 6h18', 'M8 6V4h8v2', 'M19 6l-1 14H6L5 6', 'M10 11v6', 'M14 11v6'],
  upload: ['M12 15V3', 'M7 8l5-5 5 5', 'M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4'],
  folder: ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
  file: [
    'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z',
    'M14 3v6h6',
    'M8 13h8',
    'M8 17h5',
  ],
  plus: ['M12 5v14', 'M5 12h14'],
  sun: [
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
    'M12 2v2',
    'M12 20v2',
    'M4.9 4.9l1.4 1.4',
    'M17.7 17.7l1.4 1.4',
    'M2 12h2',
    'M20 12h2',
    'M4.9 19.1l1.4-1.4',
    'M17.7 6.3l1.4-1.4',
  ],
  moon: ['M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
  restore: ['M3 12a9 9 0 1 0 3-6.7', 'M3 4v5h5'],
  sparkles: [
    'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z',
    'M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
  ],
  alert: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M12 8v4', 'M12 16h.01'],
  search: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'M21 21l-4.3-4.3'],
  pencil: ['M4 20h4L19 9l-4-4L4 16z', 'M13.5 6.5l4 4'],
  back: ['M19 12H5', 'M12 19l-7-7 7-7'],
  refresh: ['M21 12a9 9 0 1 1-3-6.7', 'M21 4v5h-5'],
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

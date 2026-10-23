import type { DocumentStatus } from '../types/api'

const LABELS: Record<DocumentStatus, string> = {
  pending: 'Pendiente',
  processing: 'Procesando',
  completed: 'Listo',
  failed: 'Error',
}

// El estado se comunica con texto, no solo con color (accesibilidad).
export function StatusBadge({ status }: { status: DocumentStatus }) {
  return <span className={`badge badge-${status}`}>{LABELS[status]}</span>
}

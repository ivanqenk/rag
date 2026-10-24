// Repite una acción cada `intervalMs` mientras `active` sea true (p. ej. mientras un documento
// se procesa en segundo plano). Se detiene sola al desmontar el componente.

import { useEffect, useRef } from 'react'

export function usePolling(action: () => void, active: boolean, intervalMs = 2000): void {
  // La última versión de la acción, sin reiniciar el temporizador en cada render.
  const latest = useRef(action)
  useEffect(() => {
    latest.current = action
  })

  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => latest.current(), intervalMs)
    return () => window.clearInterval(timer)
  }, [active, intervalMs])
}

export function isProcessing(status: string): boolean {
  return status === 'pending' || status === 'processing'
}

import { useEffect, useState } from 'react'
import { getUsage } from '../api/client'
import { formatBytes } from '../format'
import type { Usage } from '../types/api'
import { usePolling } from '../usePolling'

/** Uso de hoy y espacio ocupado, frente a los límites configurados en el servidor. */
export function UsageBar({ refreshKey }: { refreshKey: string }) {
  const [usage, setUsage] = useState<Usage | null>(null)

  const load = () => {
    getUsage()
      .then(setUsage)
      // Es informativo: si falla, simplemente no se muestra.
      .catch(() => undefined)
  }
  // Al cambiar de pantalla y cada minuto.
  useEffect(load, [refreshKey])
  usePolling(load, true, 60_000)

  if (!usage) return null
  const budget = usage.daily_budget_usd
  const nearBudget = budget > 0 && usage.cost_usd >= budget * 0.8
  return (
    <p className="usage" aria-label="Uso">
      <span className={nearBudget ? 'usage-warning' : undefined}>
        Gasto de IA hoy: ${usage.cost_usd.toFixed(4)}
        {budget > 0 && ` de $${budget.toFixed(2)}`}
      </span>
      <span>
        {usage.documents}
        {usage.max_documents > 0 && ` de ${usage.max_documents}`} documentos
      </span>
      <span>
        {formatBytes(usage.storage_bytes)}
        {usage.max_storage_bytes > 0 && ` de ${formatBytes(usage.max_storage_bytes)}`}
      </span>
    </p>
  )
}

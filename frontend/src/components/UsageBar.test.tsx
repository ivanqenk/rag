import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import type { Usage } from '../types/api'
import { UsageBar } from './UsageBar'

const USAGE: Usage = {
  day: '2026-10-24',
  cost_usd: 0.0123,
  daily_budget_usd: 1,
  queries_today: 12,
  documents_processed_today: 2,
  documents: 3,
  max_documents: 500,
  storage_bytes: 2 * 1024 * 1024,
  max_storage_bytes: 1000 * 1024 * 1024,
  queries_per_minute: 20,
  uploads_per_hour: 30,
}

describe('UsageBar', () => {
  it('muestra el gasto de hoy y el espacio frente a sus límites', async () => {
    mockFetch(jsonResponse(USAGE))
    render(<UsageBar refreshKey="a" />)

    expect(await screen.findByText('Gasto de IA hoy: $0.0123 de $1.00')).toBeInTheDocument()
    expect(screen.getByText('3 de 500 documentos')).toBeInTheDocument()
    expect(screen.getByText('2.0 MB de 1000.0 MB')).toBeInTheDocument()
  })

  it('resalta el gasto cuando se acerca al límite y omite los límites desactivados', async () => {
    mockFetch(jsonResponse({ ...USAGE, cost_usd: 0.85, max_documents: 0 }))
    render(<UsageBar refreshKey="a" />)

    expect(await screen.findByText(/\$0\.8500 de \$1\.00/)).toHaveClass('usage-warning')
    expect(screen.getByText('3 documentos')).toBeInTheDocument()
  })

  it('si no puede cargar el uso, no muestra nada', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    const { container } = render(<UsageBar refreshKey="a" />)

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container).toBeEmptyDOMElement()
  })
})

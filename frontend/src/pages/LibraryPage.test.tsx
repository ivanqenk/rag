import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeDocument } from '../test/fixtures'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { LibraryPage } from './LibraryPage'

const page = (items: unknown[]) => jsonResponse({ items, total: items.length, limit: 50, offset: 0 })

describe('LibraryPage', () => {
  it('muestra un mensaje cuando no hay documentos', async () => {
    mockFetch(page([]))
    render(<LibraryPage />)

    expect(screen.getByText('Cargando documentos…')).toBeInTheDocument()
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
  })

  it('lista los documentos con su estado y el error de los fallidos', async () => {
    mockFetch(
      page([
        makeDocument(),
        makeDocument({
          id: '22222222-2222-4222-8222-222222222222',
          original_filename: 'escaneado.pdf',
          status: 'failed',
          error_message: 'El PDF no contiene texto extraíble.',
        }),
      ]),
    )
    render(<LibraryPage />)

    // findByText es mucho más rápido que findByRole en jsdom con tablas.
    const okRow = (await screen.findByText('manual.pdf')).closest('tr')!
    expect(within(okRow).getByText('Listo')).toBeInTheDocument()
    expect(within(okRow).getByText('2.0 KB')).toBeInTheDocument()
    const failedRow = screen.getByText('escaneado.pdf').closest('tr')!
    expect(within(failedRow).getByText('Error')).toBeInTheDocument()
    expect(within(failedRow).getByText(/no contiene texto/)).toBeInTheDocument()
    expect(within(failedRow).getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })

  it('permite reintentar si la carga falla', async () => {
    mockFetch(new TypeError('Failed to fetch'), page([]))
    render(<LibraryPage />)

    expect(await screen.findByText(/No se pudo conectar/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
  })

  it('pide confirmación antes de eliminar y recarga la lista', async () => {
    const fetchSpy = mockFetch(page([makeDocument()]), new Response(null, { status: 204 }), page([]))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<LibraryPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar manual.pdf' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
    expect(fetchSpy.mock.calls[1][1]?.method).toBe('DELETE')
  })

  it('no elimina si el usuario cancela', async () => {
    const fetchSpy = mockFetch(page([makeDocument()]))
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<LibraryPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar manual.pdf' }))

    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })
})

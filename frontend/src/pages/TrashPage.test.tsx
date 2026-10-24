import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeDocument } from '../test/fixtures'
import { jsonResponse, mockApi, requests } from '../test/mockFetch'
import { TrashPage } from './TrashPage'

const TRASHED = makeDocument({ deleted_at: '2026-10-24T10:00:00Z' })
const trashPage = (items: unknown[]) =>
  jsonResponse({ items, total: items.length, limit: 100, offset: 0, retention_days: 30 })

describe('TrashPage', () => {
  it('lista los documentos con la fecha en que se borrarán', async () => {
    mockApi({ 'GET /api/v1/trash': trashPage([TRASHED]) })
    render(<TrashPage />)

    const row = (await screen.findByText('manual.pdf')).closest('tr')!
    // 24 oct + 30 días = 23 nov.
    expect(within(row).getByText(/23 nov 2026/)).toBeInTheDocument()
    expect(screen.getByText(/se conservan 30 días/)).toBeInTheDocument()
  })

  it('restaura un documento', async () => {
    const spy = mockApi({
      'GET /api/v1/trash': [trashPage([TRASHED]), trashPage([])],
      [`POST /api/v1/trash/${TRASHED.id}/restore`]: jsonResponse({ ...TRASHED, deleted_at: null }),
    })
    render(<TrashPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Restaurar manual.pdf' }))

    expect(await screen.findByText('La papelera está vacía.')).toBeInTheDocument()
    expect(requests(spy)).toContain(`POST /api/v1/trash/${TRASHED.id}/restore`)
  })

  it('elimina definitivamente solo tras confirmar', async () => {
    const spy = mockApi({
      'GET /api/v1/trash': [trashPage([TRASHED]), trashPage([])],
      [`DELETE /api/v1/trash/${TRASHED.id}`]: new Response(null, { status: 204 }),
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    render(<TrashPage />)
    const button = await screen.findByRole('button', {
      name: 'Eliminar definitivamente manual.pdf',
    })

    await userEvent.click(button)
    expect(requests(spy).some((r) => r.startsWith('DELETE'))).toBe(false)

    await userEvent.click(button)
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('No se puede deshacer'))
    expect(await screen.findByText('La papelera está vacía.')).toBeInTheDocument()
    expect(requests(spy)).toContain(`DELETE /api/v1/trash/${TRASHED.id}`)
  })

  it('vacía la papelera tras confirmar', async () => {
    const spy = mockApi({
      'GET /api/v1/trash': [trashPage([TRASHED]), trashPage([])],
      'DELETE /api/v1/trash': new Response(null, { status: 204 }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<TrashPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Vaciar papelera' }))

    expect(await screen.findByText('La papelera está vacía.')).toBeInTheDocument()
    expect(requests(spy)).toContain('DELETE /api/v1/trash')
  })
})

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeDocument, makeFolder } from '../test/fixtures'
import { jsonResponse, mockApi, requests } from '../test/mockFetch'
import { LibraryPage } from './LibraryPage'

const page = (items: unknown[]) => jsonResponse({ items, total: items.length, limit: 50, offset: 0 })
const DOC = makeDocument()
const FOLDER = makeFolder()

describe('LibraryPage', () => {
  it('muestra un mensaje cuando no hay documentos', async () => {
    mockApi({ 'GET /api/v1/documents': page([]), 'GET /api/v1/folders': jsonResponse([]) })
    render(<LibraryPage />)

    expect(screen.getByText('Cargando documentos…')).toBeInTheDocument()
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
  })

  it('lista los documentos con su estado y el error de los fallidos', async () => {
    mockApi({
      'GET /api/v1/documents': page([
        DOC,
        makeDocument({
          id: '33333333-3333-4333-8333-333333333333',
          original_filename: 'escaneado.pdf',
          status: 'failed',
          error_message: 'El PDF no contiene texto extraíble.',
        }),
      ]),
      'GET /api/v1/folders': jsonResponse([]),
    })
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
    mockApi({
      'GET /api/v1/documents': [new TypeError('Failed to fetch'), page([])],
      'GET /api/v1/folders': jsonResponse([]),
    })
    render(<LibraryPage />)

    expect(await screen.findByText(/No se pudo conectar/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
  })

  it('pide confirmación, avisa de la papelera y recarga la lista', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': [page([DOC]), page([])],
      'GET /api/v1/folders': jsonResponse([]),
      [`DELETE /api/v1/documents/${DOC.id}`]: new Response(null, { status: 204 }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<LibraryPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar manual.pdf' }))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('papelera'))
    expect(await screen.findByText(/Aún no hay documentos/)).toBeInTheDocument()
    expect(requests(spy)).toContain(`DELETE /api/v1/documents/${DOC.id}`)
  })

  it('no elimina si el usuario cancela', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': page([DOC]),
      'GET /api/v1/folders': jsonResponse([]),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<LibraryPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar manual.pdf' }))

    expect(requests(spy).some((r) => r.startsWith('DELETE'))).toBe(false)
  })

  it('crea carpetas', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': page([]),
      'GET /api/v1/folders': [jsonResponse([]), jsonResponse([FOLDER])],
      'POST /api/v1/folders': jsonResponse(FOLDER, 201),
    })
    render(<LibraryPage />)

    await userEvent.type(await screen.findByLabelText('Nombre de la nueva carpeta'), 'Contratos')
    await userEvent.click(screen.getByRole('button', { name: 'Crear carpeta' }))

    expect(await screen.findByRole('link', { name: /Contratos/ })).toHaveAttribute(
      'href',
      `#/biblioteca?carpeta=${FOLDER.id}`,
    )
    const create = spy.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(create[1]?.body as string)).toEqual({ name: 'Contratos' })
    expect(screen.getByLabelText('Nombre de la nueva carpeta')).toHaveValue('')
  })

  it('muestra solo los documentos de la carpeta elegida', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': page([makeDocument({ folder_id: FOLDER.id })]),
      'GET /api/v1/folders': jsonResponse([FOLDER]),
    })
    render(<LibraryPage folderId={FOLDER.id} />)

    expect(await screen.findByRole('heading', { name: 'Contratos' })).toBeInTheDocument()
    expect(requests(spy)).toContain(`GET /api/v1/documents?limit=50&offset=0&folder_id=${FOLDER.id}`)
    expect(screen.getByRole('link', { name: 'Preguntar a esta carpeta' })).toHaveAttribute(
      'href',
      `#/preguntar?carpeta=${FOLDER.id}`,
    )
    expect(screen.getByText('Se guardará en «Contratos».')).toBeInTheDocument()
  })

  it('mueve un documento a otra carpeta', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': page([DOC]),
      'GET /api/v1/folders': jsonResponse([FOLDER]),
      [`PATCH /api/v1/documents/${DOC.id}`]: jsonResponse({ ...DOC, folder_id: FOLDER.id }),
    })
    render(<LibraryPage />)

    await screen.findByText('manual.pdf')
    await userEvent.selectOptions(screen.getByLabelText('Carpeta de manual.pdf'), 'Contratos')

    const patch = spy.mock.calls.find(([, init]) => init?.method === 'PATCH')!
    expect(JSON.parse(patch[1]?.body as string)).toEqual({ folder_id: FOLDER.id })
  })

  it('al eliminar una carpeta avisa de que sus documentos se conservan', async () => {
    const spy = mockApi({
      'GET /api/v1/documents': page([]),
      'GET /api/v1/folders': jsonResponse([FOLDER]),
      [`DELETE /api/v1/folders/${FOLDER.id}`]: new Response(null, { status: 204 }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<LibraryPage folderId={FOLDER.id} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar carpeta' }))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('no se borran'))
    expect(requests(spy)).toContain(`DELETE /api/v1/folders/${FOLDER.id}`)
  })
})

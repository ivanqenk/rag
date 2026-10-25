import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { makeDocument } from '../test/fixtures'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { DocumentPage } from './DocumentPage'

const ID = '11111111-1111-4111-8111-111111111111'

describe('DocumentPage', () => {
  it('muestra el resumen del documento como texto', async () => {
    const summary = 'Resumen <b>con</b> etiquetas <img src=x onerror="alert(1)">'
    mockFetch(jsonResponse(makeDocument({ summary })))
    const { container } = render(<DocumentPage id={ID} />)

    expect(await screen.findByText(summary)).toBeInTheDocument()
    expect(screen.getByText(/Generado automáticamente por IA/)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('enlaza el PDF original en una pestaña nueva', async () => {
    const document = makeDocument()
    mockFetch(jsonResponse(document))
    render(<DocumentPage id={document.id} />)

    const link = await screen.findByRole('link', { name: 'Ver PDF original' })
    expect(link).toHaveAttribute('href', `/api/v1/documents/${document.id}/file`)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByRole('link', { name: 'Preguntar sobre este documento' })).toHaveAttribute(
      'href',
      `#/preguntar?documento=${document.id}`,
    )
  })

  it('permite generar el resumen si no lo tiene', async () => {
    const fetchSpy = mockFetch(
      jsonResponse(makeDocument({ summary: null })),
      jsonResponse(makeDocument({ summary: 'Un manual de vacaciones.' })),
    )
    render(<DocumentPage id={ID} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Generar resumen' }))

    expect(await screen.findByText('Un manual de vacaciones.')).toBeInTheDocument()
    expect(fetchSpy.mock.calls[1][0]).toBe(`/api/v1/documents/${ID}/reprocess`)
    expect(fetchSpy.mock.calls[1][1]?.method).toBe('POST')
  })

  it('avisa si no se pudo generar el resumen', async () => {
    mockFetch(
      jsonResponse(makeDocument({ summary: null })),
      jsonResponse(makeDocument({ summary: null })),
    )
    render(<DocumentPage id={ID} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Generar resumen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar el resumen')
  })

  it('no muestra resumen en documentos fallidos', async () => {
    mockFetch(jsonResponse(makeDocument({ status: 'failed', summary: null })))
    render(<DocumentPage id={ID} />)

    expect(await screen.findByText('manual.pdf')).toBeInTheDocument()
    expect(screen.queryByText('Resumen')).not.toBeInTheDocument()
  })

  it('explica cuando el documento no existe', async () => {
    mockFetch(jsonResponse({ detail: 'Documento no encontrado' }, 404))
    render(<DocumentPage id={ID} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('no existe o fue eliminado')
  })

  it('avisa si está en la papelera y permite restaurarlo', async () => {
    const trashed = makeDocument({ deleted_at: '2026-10-24T10:00:00Z' })
    const fetchSpy = mockFetch(jsonResponse(trashed), jsonResponse({ ...trashed, deleted_at: null }))
    render(<DocumentPage id={trashed.id} />)

    expect(await screen.findByText(/está en la/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Preguntar sobre este documento' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Restaurar' }))

    expect(await screen.findByRole('link', { name: 'Preguntar sobre este documento' })).toBeInTheDocument()
    expect(screen.queryByText(/está en la/)).toBeNull()
    expect(fetchSpy.mock.calls[1][0]).toBe(`/api/v1/trash/${trashed.id}/restore`)
  })
})

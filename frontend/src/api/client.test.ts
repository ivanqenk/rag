import { describe, expect, it } from 'vitest'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { ApiError, askQuestion, deleteDocument, listDocuments } from './client'

describe('cliente de la API', () => {
  it('devuelve el JSON de una respuesta correcta', async () => {
    mockFetch(jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }))

    await expect(listDocuments()).resolves.toEqual({ items: [], total: 0, limit: 50, offset: 0 })
  })

  it('usa el mensaje "detail" del backend en los errores', async () => {
    mockFetch(jsonResponse({ detail: 'El proveedor de LLM no tiene saldo.' }, 503))

    await expect(askQuestion('hola')).rejects.toEqual(
      new ApiError(503, 'El proveedor de LLM no tiene saldo.'),
    )
  })

  it('resume las validaciones de FastAPI (lista) en un mensaje genérico', async () => {
    mockFetch(jsonResponse({ detail: [{ loc: ['body'], msg: 'x' }] }, 422))

    await expect(askQuestion('hola')).rejects.toThrow('Los datos enviados no son válidos.')
  })

  it('no muestra detalles internos si el servidor devuelve HTML o texto', async () => {
    mockFetch(new Response('<html>Traceback (most recent call last)…</html>', { status: 500 }))

    await expect(listDocuments()).rejects.toThrow('Error del servidor. Inténtalo de nuevo más tarde.')
  })

  it('explica el 413 de nginx (página HTML) como archivo demasiado grande', async () => {
    mockFetch(new Response('<html>413 Request Entity Too Large</html>', { status: 413 }))

    await expect(listDocuments()).rejects.toThrow('El archivo es demasiado grande.')
  })

  it('traduce un fallo de red a un mensaje comprensible', async () => {
    mockFetch(new TypeError('Failed to fetch'))

    await expect(listDocuments()).rejects.toThrow('No se pudo conectar con el servidor')
  })

  it('acepta respuestas 204 sin cuerpo', async () => {
    mockFetch(new Response(null, { status: 204 }))

    await expect(deleteDocument('abc')).resolves.toBeUndefined()
  })
})

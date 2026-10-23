import { describe, expect, it } from 'vitest'
import { parseRoute, routes } from './router'

describe('parseRoute', () => {
  it.each([
    ['', { name: 'library' }],
    ['#/biblioteca', { name: 'library' }],
    ['#/preguntar', { name: 'ask' }],
    ['#/documentos/abc-123', { name: 'document', id: 'abc-123' }],
    ['#/documentos/../../etc', { name: 'library' }],
    ['#/desconocida', { name: 'library' }],
  ])('%s', (hash, expected) => {
    expect(parseRoute(hash)).toEqual(expected)
  })

  it('las rutas generadas se pueden volver a leer', () => {
    expect(parseRoute(routes.document('abc-123'))).toEqual({ name: 'document', id: 'abc-123' })
  })
})

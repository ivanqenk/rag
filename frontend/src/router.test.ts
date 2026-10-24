import { describe, expect, it } from 'vitest'
import { parseRoute, routes } from './router'

describe('parseRoute', () => {
  it.each([
    ['', { name: 'library' }],
    ['#/biblioteca', { name: 'library' }],
    ['#/preguntar', { name: 'ask' }],
    ['#/preguntar?documento=abc-123', { name: 'ask', documentId: 'abc-123' }],
    ['#/preguntar?documento=../x', { name: 'library' }],
    ['#/documentos/abc-123', { name: 'document', id: 'abc-123' }],
    ['#/documentos/../../etc', { name: 'library' }],
    ['#/desconocida', { name: 'library' }],
  ])('%s', (hash, expected) => {
    expect(parseRoute(hash)).toEqual(expected)
  })

  it('las rutas generadas se pueden volver a leer', () => {
    expect(parseRoute(routes.document('abc-123'))).toEqual({ name: 'document', id: 'abc-123' })
    expect(parseRoute(routes.askAbout('abc-123'))).toEqual({ name: 'ask', documentId: 'abc-123' })
  })
})

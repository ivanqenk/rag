import { describe, expect, it } from 'vitest'
import { parseRoute, routes } from './router'

describe('parseRoute', () => {
  it.each([
    ['', { name: 'library' }],
    ['#/biblioteca', { name: 'library' }],
    ['#/preguntar', { name: 'ask' }],
    ['#/preguntar?documento=abc-123', { name: 'ask', documentId: 'abc-123' }],
    ['#/preguntar?documento=../x', { name: 'library' }],
    ['#/preguntar?carpeta=f-1', { name: 'ask', folderId: 'f-1' }],
    ['#/biblioteca?carpeta=f-1', { name: 'library', folderId: 'f-1' }],
    ['#/papelera', { name: 'trash' }],
    ['#/documentos/abc-123', { name: 'document', id: 'abc-123' }],
    ['#/documentos/../../etc', { name: 'library' }],
    ['#/desconocida', { name: 'library' }],
  ])('%s', (hash, expected) => {
    expect(parseRoute(hash)).toEqual(expected)
  })

  it('las rutas generadas se pueden volver a leer', () => {
    expect(parseRoute(routes.document('abc-123'))).toEqual({ name: 'document', id: 'abc-123' })
    expect(parseRoute(routes.askAbout('abc-123'))).toEqual({ name: 'ask', documentId: 'abc-123' })
    expect(parseRoute(routes.askFolder('f-1'))).toEqual({ name: 'ask', folderId: 'f-1' })
    expect(parseRoute(routes.folder('f-1'))).toEqual({ name: 'library', folderId: 'f-1' })
  })
})

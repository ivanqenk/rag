// Navegación mínima basada en el hash de la URL (#/biblioteca, #/documentos/<id>…).
// Para tres pantallas no compensa añadir una librería de rutas.

import { useEffect, useState } from 'react'

export type Route =
  | { name: 'library' }
  | { name: 'ask'; documentId?: string }
  | { name: 'document'; id: string }

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '')
  const documentMatch = path.match(/^\/documentos\/([\w-]+)$/)
  if (documentMatch) return { name: 'document', id: documentMatch[1] }
  if (path === '/preguntar') return { name: 'ask' }
  // Preguntar solo sobre un documento: #/preguntar?documento=<id>
  const askMatch = path.match(/^\/preguntar\?documento=([\w-]+)$/)
  if (askMatch) return { name: 'ask', documentId: askMatch[1] }
  return { name: 'library' }
}

export const routes = {
  library: '#/biblioteca',
  ask: '#/preguntar',
  askAbout: (documentId: string) => `#/preguntar?documento=${encodeURIComponent(documentId)}`,
  document: (id: string) => `#/documentos/${encodeURIComponent(id)}`,
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

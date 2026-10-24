// Navegación mínima basada en el hash de la URL (#/biblioteca, #/documentos/<id>…).
// Para cuatro pantallas no compensa añadir una librería de rutas.

import { useEffect, useState } from 'react'

export type Route =
  | { name: 'library'; folderId?: string }
  | { name: 'ask'; documentId?: string; folderId?: string }
  | { name: 'document'; id: string }
  | { name: 'trash' }

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '')
  const documentMatch = path.match(/^\/documentos\/([\w-]+)$/)
  if (documentMatch) return { name: 'document', id: documentMatch[1] }
  if (path === '/preguntar') return { name: 'ask' }
  // Preguntar solo sobre un documento o una carpeta: #/preguntar?documento=<id> / ?carpeta=<id>
  const askMatch = path.match(/^\/preguntar\?(documento|carpeta)=([\w-]+)$/)
  if (askMatch) {
    return askMatch[1] === 'documento'
      ? { name: 'ask', documentId: askMatch[2] }
      : { name: 'ask', folderId: askMatch[2] }
  }
  const folderMatch = path.match(/^\/biblioteca\?carpeta=([\w-]+)$/)
  if (folderMatch) return { name: 'library', folderId: folderMatch[1] }
  if (path === '/papelera') return { name: 'trash' }
  return { name: 'library' }
}

export const routes = {
  library: '#/biblioteca',
  ask: '#/preguntar',
  askAbout: (documentId: string) => `#/preguntar?documento=${encodeURIComponent(documentId)}`,
  askFolder: (folderId: string) => `#/preguntar?carpeta=${encodeURIComponent(folderId)}`,
  folder: (folderId: string) => `#/biblioteca?carpeta=${encodeURIComponent(folderId)}`,
  trash: '#/papelera',
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

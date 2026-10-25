// Cliente HTTP tipado. Es el único lugar que conoce las URLs y el formato de errores de la API.

import type {
  AnswerStyle,
  DocumentPage,
  DocumentRead,
  Folder,
  QueryResponse,
  TrashPage,
  Usage,
} from '../types/api'

/** Error con un mensaje apto para mostrar al usuario (nunca trazas ni detalles internos). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const NETWORK_ERROR = 'No se pudo conectar con el servidor. Comprueba que el backend está en marcha.'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(0, NETWORK_ERROR)
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  // El backend devuelve {"detail": "mensaje"} con mensajes ya pensados para el usuario.
  // Las validaciones automáticas de FastAPI devuelven una lista: se resume en un texto genérico.
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Respuesta sin JSON (p. ej. un proxy caído): se usa el mensaje genérico.
  }
  // El proxy (nginx) corta los archivos enormes antes de llegar al backend, con una página HTML.
  if (response.status === 413) return 'El archivo es demasiado grande.'
  if (response.status === 422) return 'Los datos enviados no son válidos.'
  if (response.status >= 500) return 'Error del servidor. Inténtalo de nuevo más tarde.'
  return `Error inesperado (${response.status}).`
}

export function listDocuments(limit = 50, offset = 0, folderId?: string): Promise<DocumentPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (folderId) params.set('folder_id', folderId)
  return request<DocumentPage>(`/api/v1/documents?${params}`)
}

export function getDocument(id: string): Promise<DocumentRead> {
  return request<DocumentRead>(`/api/v1/documents/${encodeURIComponent(id)}`)
}

export function uploadDocument(file: File, folderId?: string): Promise<DocumentRead> {
  const body = new FormData()
  body.append('file', file)
  if (folderId) body.append('folder_id', folderId)
  return request<DocumentRead>('/api/v1/documents', { method: 'POST', body })
}

/** Mueve el documento a la papelera (se puede restaurar). */
export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/v1/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** Mueve el documento a una carpeta, o lo saca de ella con `null`. */
export function moveDocument(id: string, folderId: string | null): Promise<DocumentRead> {
  return request<DocumentRead>(`/api/v1/documents/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
}

// --- Carpetas ---------------------------------------------------------------------------

export function listFolders(): Promise<Folder[]> {
  return request<Folder[]>('/api/v1/folders')
}

export function createFolder(name: string): Promise<Folder> {
  return request<Folder>('/api/v1/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function renameFolder(id: string, name: string): Promise<Folder> {
  return request<Folder>(`/api/v1/folders/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

/** Borra la carpeta; sus documentos quedan sin carpeta. */
export function deleteFolder(id: string): Promise<void> {
  return request<void>(`/api/v1/folders/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// --- Papelera ---------------------------------------------------------------------------

export function listTrash(): Promise<TrashPage> {
  return request<TrashPage>('/api/v1/trash?limit=100')
}

export function restoreDocument(id: string): Promise<DocumentRead> {
  return request<DocumentRead>(`/api/v1/trash/${encodeURIComponent(id)}/restore`, {
    method: 'POST',
  })
}

/** Borra del todo un documento de la papelera. No se puede deshacer. */
export function deletePermanently(id: string): Promise<void> {
  return request<void>(`/api/v1/trash/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function emptyTrash(): Promise<void> {
  return request<void>('/api/v1/trash', { method: 'DELETE' })
}

/** URL del PDF original. Los visores de PDF del navegador abren `#page=N` en esa página. */
export function documentFileUrl(id: string, page?: number | null): string {
  const url = `/api/v1/documents/${encodeURIComponent(id)}/file`
  return page ? `${url}#page=${page}` : url
}

export function reprocessDocument(id: string): Promise<DocumentRead> {
  return request<DocumentRead>(`/api/v1/documents/${encodeURIComponent(id)}/reprocess`, {
    method: 'POST',
  })
}

/** Limita la pregunta a una carpeta, o a un documento y opcionalmente una de sus páginas. */
export type QueryScope = { folderId: string } | { documentId: string; pageNumber?: number }

/** Un turno anterior de la conversación (solo vive en el navegador). */
export interface HistoryTurn {
  question: string
  answer: string
}

export function askQuestion(
  question: string,
  scope?: QueryScope,
  style: AnswerStyle = 'brief',
  history: HistoryTurn[] = [],
): Promise<QueryResponse> {
  return request<QueryResponse>('/api/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      answer_style: style,
      folder_id: scope && 'folderId' in scope ? scope.folderId : undefined,
      document_id: scope && 'documentId' in scope ? scope.documentId : undefined,
      page_number: scope && 'documentId' in scope ? scope.pageNumber : undefined,
      history: history.length > 0 ? history : undefined,
    }),
  })
}

export function getUsage(): Promise<Usage> {
  return request<Usage>('/api/v1/usage')
}

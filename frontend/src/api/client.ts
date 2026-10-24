// Cliente HTTP tipado. Es el único lugar que conoce las URLs y el formato de errores de la API.

import type { DocumentPage, DocumentRead, QueryResponse } from '../types/api'

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

export function listDocuments(limit = 50, offset = 0): Promise<DocumentPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request<DocumentPage>(`/api/v1/documents?${params}`)
}

export function getDocument(id: string): Promise<DocumentRead> {
  return request<DocumentRead>(`/api/v1/documents/${encodeURIComponent(id)}`)
}

export function uploadDocument(file: File): Promise<DocumentRead> {
  const body = new FormData()
  body.append('file', file)
  return request<DocumentRead>('/api/v1/documents', { method: 'POST', body })
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/v1/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
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

export function askQuestion(question: string): Promise<QueryResponse> {
  return request<QueryResponse>('/api/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

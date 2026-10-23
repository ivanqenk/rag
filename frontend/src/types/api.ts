// Tipos de las respuestas de la API. Reflejan los esquemas Pydantic del backend
// (backend/app/schemas/). Si cambias uno, cambia el otro.

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface DocumentRead {
  id: string
  original_filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  error_message: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
}

export interface DocumentPage {
  items: DocumentRead[]
  total: number
  limit: number
  offset: number
}

export interface Source {
  document_id: string
  filename: string
  page_number: number | null
  chunk_id: string
  excerpt: string
  score: number
}

export interface QueryResponse {
  // Texto generado por un LLM: mostrar siempre como texto, nunca como HTML.
  answer: string
  sources: Source[]
  insufficient_evidence: boolean
}

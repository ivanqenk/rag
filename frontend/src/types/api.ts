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
  // Resumen generado por un LLM (null si no se pudo generar): mostrar como texto.
  summary: string | null
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
  // 'summary': la fuente es el resumen del documento (sin fragmento, página ni score).
  source_type: 'chunk' | 'summary'
  chunk_id: string | null
  excerpt: string
  score: number | null
}

export interface QueryResponse {
  // Texto generado por un LLM: mostrar siempre como texto, nunca como HTML.
  answer: string
  sources: Source[]
  insufficient_evidence: boolean
}

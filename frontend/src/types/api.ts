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
  folder_id: string | null
  // En la papelera desde esta fecha; null si está activo.
  deleted_at: string | null
}

export interface Folder {
  id: string
  name: string
  created_at: string
  document_count: number
}

export interface DocumentPage {
  items: DocumentRead[]
  total: number
  limit: number
  offset: number
}

export interface TrashPage extends DocumentPage {
  // Días que se conservan en la papelera antes de borrarse del todo.
  retention_days: number
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

// brief: una o dos frases; detailed: resumen y puntos (numerados si son pasos).
export type AnswerStyle = 'brief' | 'detailed'

export interface AnswerPoint {
  // Texto generado por un LLM: mostrar siempre como texto, nunca como HTML.
  text: string
  // Posiciones (desde 0) en QueryResponse.sources de las fuentes que lo respaldan.
  sources: number[]
}

export interface QueryResponse {
  // Texto generado por un LLM: mostrar siempre como texto, nunca como HTML. Puede estar vacío
  // en respuestas detalladas si el resumen no superó la verificación (quedan los puntos).
  answer: string
  sources: Source[]
  insufficient_evidence: boolean
  answer_style: AnswerStyle
  points: AnswerPoint[]
  // Los puntos son pasos de un procedimiento: mostrarlos numerados.
  points_ordered: boolean
}

export interface Usage {
  day: string
  // Gasto estimado de hoy (UTC) en el proveedor de IA y el máximo diario (0 = sin límite).
  cost_usd: number
  daily_budget_usd: number
  queries_today: number
  documents_processed_today: number
  // Incluyen la papelera. max_* = 0: sin límite.
  documents: number
  max_documents: number
  storage_bytes: number
  max_storage_bytes: number
  queries_per_minute: number
  uploads_per_hour: number
}

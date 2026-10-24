import type { DocumentRead } from '../types/api'

export function makeDocument(overrides: Partial<DocumentRead> = {}): DocumentRead {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    original_filename: 'manual.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    status: 'completed',
    error_message: null,
    created_at: '2026-10-23T10:00:00Z',
    updated_at: '2026-10-23T10:00:01Z',
    processed_at: '2026-10-23T10:00:01Z',
    summary: 'Manual de recursos humanos con la política de vacaciones y gastos.',
    ...overrides,
  }
}

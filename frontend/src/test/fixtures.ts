import type { DocumentRead, Folder } from '../types/api'

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
    folder_id: null,
    deleted_at: null,
    ...overrides,
  }
}

export function makeFolder(overrides: Partial<Folder> = {}): Folder {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    name: 'Contratos',
    created_at: '2026-10-24T10:00:00Z',
    document_count: 1,
    ...overrides,
  }
}

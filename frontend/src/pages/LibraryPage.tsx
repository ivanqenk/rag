import { useCallback, useEffect, useState } from 'react'
import { ApiError, deleteDocument, listDocuments, reprocessDocument } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { UploadForm } from '../components/UploadForm'
import { formatBytes, formatDate } from '../format'
import { routes } from '../router'
import type { DocumentRead } from '../types/api'

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; documents: DocumentRead[]; total: number }

async function fetchListState(): Promise<ListState> {
  try {
    const page = await listDocuments()
    return { kind: 'ready', documents: page.items, total: page.total }
  } catch (error) {
    return {
      kind: 'error',
      message: error instanceof ApiError ? error.message : 'No se pudo cargar la biblioteca.',
    }
  }
}

export function LibraryPage() {
  const [state, setState] = useState<ListState>({ kind: 'loading' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => setState(await fetchListState()), [])

  useEffect(() => {
    let cancelled = false
    void fetchListState().then((next) => !cancelled && setState(next))
    return () => {
      cancelled = true
    }
  }, [])

  async function runAction(id: string, action: () => Promise<unknown>) {
    setActionError(null)
    setBusyId(id)
    try {
      await action()
      await load()
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'La operación no se completó.')
    } finally {
      setBusyId(null)
    }
  }

  function onDelete(document: DocumentRead) {
    const confirmed = window.confirm(
      `¿Eliminar «${document.original_filename}»? Se borrarán el archivo y sus datos. No se puede deshacer.`,
    )
    if (confirmed) void runAction(document.id, () => deleteDocument(document.id))
  }

  return (
    <>
      <UploadForm onUploaded={() => void load()} />

      <section className="card" aria-labelledby="library-title">
        <h2 id="library-title">Biblioteca</h2>
        {actionError && (
          <p className="error" role="alert">
            {actionError}
          </p>
        )}
        {state.kind === 'loading' && <p className="info">Cargando documentos…</p>}
        {state.kind === 'error' && (
          <div role="alert">
            <p className="error">{state.message}</p>
            <button type="button" onClick={() => void load()}>
              Reintentar
            </button>
          </div>
        )}
        {state.kind === 'ready' && state.documents.length === 0 && (
          <p className="empty">Aún no hay documentos. Sube un PDF para empezar.</p>
        )}
        {state.kind === 'ready' && state.documents.length > 0 && (
          <>
            <table>
              <caption className="visually-hidden">
                {state.total} documento{state.total === 1 ? '' : 's'}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Nombre</th>
                  <th scope="col">Tamaño</th>
                  <th scope="col">Subido</th>
                  <th scope="col">Estado</th>
                  <th scope="col">
                    <span className="visually-hidden">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.documents.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <a href={routes.document(document.id)}>{document.original_filename}</a>
                      {document.status === 'failed' && document.error_message && (
                        <div className="row-error">{document.error_message}</div>
                      )}
                    </td>
                    <td>{formatBytes(document.size_bytes)}</td>
                    <td>{formatDate(document.created_at)}</td>
                    <td>
                      <StatusBadge status={document.status} />
                    </td>
                    <td className="actions">
                      {document.status === 'failed' && (
                        <button
                          type="button"
                          disabled={busyId === document.id}
                          onClick={() =>
                            void runAction(document.id, () => reprocessDocument(document.id))
                          }
                        >
                          Reintentar
                        </button>
                      )}
                      <button
                        type="button"
                        className="danger"
                        disabled={busyId === document.id}
                        aria-label={`Eliminar ${document.original_filename}`}
                        onClick={() => onDelete(document)}
                      >
                        Eliminar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {state.total > state.documents.length && (
              <p className="hint">
                Mostrando {state.documents.length} de {state.total} documentos.
              </p>
            )}
          </>
        )}
      </section>
    </>
  )
}

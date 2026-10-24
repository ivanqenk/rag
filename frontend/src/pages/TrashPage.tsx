import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  deletePermanently,
  emptyTrash,
  listTrash,
  restoreDocument,
} from '../api/client'
import { formatBytes, formatDate } from '../format'
import type { DocumentRead } from '../types/api'

const DAY_MS = 24 * 60 * 60 * 1000

type TrashState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; documents: DocumentRead[]; total: number; retentionDays: number }

async function fetchTrash(): Promise<TrashState> {
  try {
    const page = await listTrash()
    return {
      kind: 'ready',
      documents: page.items,
      total: page.total,
      retentionDays: page.retention_days,
    }
  } catch (error) {
    const message = error instanceof ApiError ? error.message : 'No se pudo cargar la papelera.'
    return { kind: 'error', message }
  }
}

/** Fecha en la que el servidor borrará del todo el documento. */
function purgeDate(deletedAt: string, retentionDays: number): string {
  return formatDate(new Date(new Date(deletedAt).getTime() + retentionDays * DAY_MS).toISOString())
}

export function TrashPage() {
  const [state, setState] = useState<TrashState>({ kind: 'loading' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => setState(await fetchTrash()), [])

  useEffect(() => {
    let cancelled = false
    void fetchTrash().then((next) => !cancelled && setState(next))
    return () => {
      cancelled = true
    }
  }, [])

  async function runAction(action: () => Promise<unknown>) {
    setActionError(null)
    setBusy(true)
    try {
      await action()
      await load()
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'La operación no se completó.')
    } finally {
      setBusy(false)
    }
  }

  function onDeletePermanently(document: DocumentRead) {
    const confirmed = window.confirm(
      `¿Eliminar definitivamente «${document.original_filename}»? No se puede deshacer.`,
    )
    if (confirmed) void runAction(() => deletePermanently(document.id))
  }

  function onEmpty() {
    const confirmed = window.confirm(
      '¿Vaciar la papelera? Todos sus documentos se borrarán definitivamente. No se puede deshacer.',
    )
    if (confirmed) void runAction(emptyTrash)
  }

  return (
    <section className="card" aria-labelledby="trash-title">
      <h2 id="trash-title">Papelera</h2>
      {state.kind === 'ready' && (
        <p className="hint">
          Los documentos eliminados se conservan {state.retentionDays} días: puedes restaurarlos
          hasta entonces. No aparecen en la biblioteca ni en las respuestas.
        </p>
      )}
      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}
      {state.kind === 'loading' && <p className="info">Cargando papelera…</p>}
      {state.kind === 'error' && (
        <div role="alert">
          <p className="error">{state.message}</p>
          <button type="button" onClick={() => void load()}>
            Reintentar
          </button>
        </div>
      )}
      {state.kind === 'ready' && state.documents.length === 0 && (
        <p className="empty">La papelera está vacía.</p>
      )}
      {state.kind === 'ready' && state.documents.length > 0 && (
        <>
          <table>
            <caption className="visually-hidden">
              {state.total} documento{state.total === 1 ? '' : 's'} en la papelera
            </caption>
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">Tamaño</th>
                <th scope="col">Eliminado</th>
                <th scope="col">Se borrará</th>
                <th scope="col">
                  <span className="visually-hidden">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {state.documents.map((document) => (
                <tr key={document.id}>
                  <td>{document.original_filename}</td>
                  <td>{formatBytes(document.size_bytes)}</td>
                  <td>{document.deleted_at ? formatDate(document.deleted_at) : '—'}</td>
                  <td>
                    {document.deleted_at ? purgeDate(document.deleted_at, state.retentionDays) : '—'}
                  </td>
                  <td className="actions">
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`Restaurar ${document.original_filename}`}
                      onClick={() => void runAction(() => restoreDocument(document.id))}
                    >
                      Restaurar
                    </button>
                    <button
                      type="button"
                      className="danger"
                      disabled={busy}
                      aria-label={`Eliminar definitivamente ${document.original_filename}`}
                      onClick={() => onDeletePermanently(document)}
                    >
                      Eliminar definitivamente
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button type="button" className="danger" disabled={busy} onClick={onEmpty}>
              Vaciar papelera
            </button>
          </p>
        </>
      )}
    </section>
  )
}

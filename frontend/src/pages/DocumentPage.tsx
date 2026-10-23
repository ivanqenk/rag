import { useEffect, useState } from 'react'
import { ApiError, getDocument } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { formatBytes, formatDate } from '../format'
import { routes } from '../router'
import type { DocumentRead } from '../types/api'

type DocumentState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; document: DocumentRead }

export function DocumentPage({ id }: { id: string }) {
  const [state, setState] = useState<DocumentState>({ kind: 'loading' })

  useEffect(() => {
    // App monta un DocumentPage nuevo (key={id}) por documento: el estado inicial ya es "loading".
    let cancelled = false
    getDocument(id)
      .then((document) => !cancelled && setState({ kind: 'ready', document }))
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof ApiError && error.status === 404
            ? 'El documento no existe o fue eliminado.'
            : error instanceof ApiError
              ? error.message
              : 'No se pudo cargar el documento.'
        setState({ kind: 'error', message })
      })
    // Evita actualizar el estado si el usuario navega a otro documento antes de la respuesta.
    return () => {
      cancelled = true
    }
  }, [id])

  return (
    <section className="card" aria-labelledby="document-title">
      <p>
        <a href={routes.library}>← Volver a la biblioteca</a>
      </p>
      {state.kind === 'loading' && <p className="info">Cargando…</p>}
      {state.kind === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.kind === 'ready' && (
        <>
          <h2 id="document-title">{state.document.original_filename}</h2>
          <dl className="metadata">
            <dt>Estado</dt>
            <dd>
              <StatusBadge status={state.document.status} />
            </dd>
            {state.document.error_message && (
              <>
                <dt>Error</dt>
                <dd>{state.document.error_message}</dd>
              </>
            )}
            <dt>Tamaño</dt>
            <dd>{formatBytes(state.document.size_bytes)}</dd>
            <dt>Subido</dt>
            <dd>{formatDate(state.document.created_at)}</dd>
            <dt>Procesado</dt>
            <dd>{state.document.processed_at ? formatDate(state.document.processed_at) : '—'}</dd>
            <dt>Identificador</dt>
            <dd>
              <code>{state.document.id}</code>
            </dd>
          </dl>
        </>
      )}
    </section>
  )
}

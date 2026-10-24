import { useEffect, useState } from 'react'
import {
  ApiError,
  documentFileUrl,
  getDocument,
  reprocessDocument,
  restoreDocument,
} from '../api/client'
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
          {state.document.deleted_at && (
            <TrashNotice
              document={state.document}
              onRestored={(document) => setState({ kind: 'ready', document })}
            />
          )}
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
          <p className="links">
            <a href={documentFileUrl(state.document.id)} target="_blank" rel="noopener noreferrer">
              Ver PDF original
            </a>
            {state.document.status === 'completed' && !state.document.deleted_at && (
              <a href={routes.askAbout(state.document.id)}>Preguntar sobre este documento</a>
            )}
          </p>
          <Summary
            document={state.document}
            onUpdated={(document) => setState({ kind: 'ready', document })}
          />
        </>
      )}
    </section>
  )
}

function Summary({
  document,
  onUpdated,
}: {
  document: DocumentRead
  onUpdated: (document: DocumentRead) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (document.status !== 'completed') return null
  // En la papelera no se puede reprocesar (el servidor respondería 409).
  const canRegenerate = !document.deleted_at

  async function regenerate() {
    setBusy(true)
    setError(null)
    try {
      // Reprocesar vuelve a generar fragmentos, embeddings y resumen.
      const updated = await reprocessDocument(document.id)
      if (!updated.summary) setError('No se pudo generar el resumen. Inténtalo más tarde.')
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el resumen.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="summary-title">
      <h3 id="summary-title">Resumen</h3>
      {document.summary ? (
        <>
          {/* Generado por un LLM: se muestra como texto, nunca como HTML (ver AskPage). */}
          <p className="answer">{document.summary}</p>
          <p className="hint">Generado automáticamente por IA: puede contener errores.</p>
        </>
      ) : (
        <>
          <p className="hint">
            No hay resumen disponible: el proveedor de IA no estaba configurado o falló.
          </p>
          {canRegenerate && (
            <button type="button" disabled={busy} onClick={() => void regenerate()}>
              {busy ? 'Generando…' : 'Generar resumen'}
            </button>
          )}
        </>
      )}
      <div aria-live="polite">
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  )
}

function TrashNotice({
  document,
  onRestored,
}: {
  document: DocumentRead
  onRestored: (document: DocumentRead) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function restore() {
    setBusy(true)
    setError(null)
    try {
      onRestored(await restoreDocument(document.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo restaurar el documento.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="notice-box" role="status">
      <p>
        Este documento está en la <a href={routes.trash}>papelera</a>: no aparece en la biblioteca
        ni en las respuestas.
      </p>
      <button type="button" disabled={busy} onClick={() => void restore()}>
        {busy ? 'Restaurando…' : 'Restaurar'}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

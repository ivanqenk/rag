import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, askQuestion, documentFileUrl, getDocument } from '../api/client'
import { routes } from '../router'
import type { QueryResponse } from '../types/api'

// Debe coincidir con MAX_QUERY_CHARS del backend.
const MAX_QUESTION_CHARS = 1000

type AskState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'answered'; response: QueryResponse }
  | { kind: 'error'; message: string }

// Pregunta limitada a un documento (desde su página de detalle): solo hace falta su nombre.
type ScopeState =
  | { kind: 'loading' }
  | { kind: 'ready'; filename: string }
  | { kind: 'error'; message: string }

/** Sin `documentId` pregunta a todos los documentos; con él, solo a ese (y a una página). */
export function AskPage({ documentId }: { documentId?: string }) {
  const [question, setQuestion] = useState('')
  const [page, setPage] = useState('')
  const [state, setState] = useState<AskState>({ kind: 'idle' })
  const [scope, setScope] = useState<ScopeState>({ kind: 'loading' })

  useEffect(() => {
    if (!documentId) return
    let cancelled = false
    getDocument(documentId)
      .then((document) => {
        if (!cancelled) setScope({ kind: 'ready', filename: document.original_filename })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof ApiError && error.status === 404
            ? 'El documento no existe.'
            : 'No se pudo cargar el documento.'
        setScope({ kind: 'error', message })
      })
    return () => {
      cancelled = true
    }
  }, [documentId])

  const pageNumber = Number.parseInt(page, 10)
  const validPage = page === '' || (Number.isInteger(pageNumber) && pageNumber >= 1)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    setState({ kind: 'loading' })
    try {
      const response = await askQuestion(
        trimmed,
        documentId ? { documentId, pageNumber: page ? pageNumber : undefined } : undefined,
      )
      setState({ kind: 'answered', response })
    } catch (error) {
      setState({
        kind: 'error',
        message: error instanceof ApiError ? error.message : 'No se pudo obtener una respuesta.',
      })
    }
  }

  const loading = state.kind === 'loading'
  const scopeBlocked = documentId !== undefined && scope.kind !== 'ready'

  return (
    <>
      <section className="card" aria-labelledby="ask-title">
        <h2 id="ask-title">
          {documentId ? 'Preguntar sobre un documento' : 'Preguntar a tus documentos'}
        </h2>
        {documentId && (
          <div className="scope">
            {scope.kind === 'loading' && <span className="hint">Cargando documento…</span>}
            {scope.kind === 'error' && (
              <span className="error" role="alert">
                {scope.message}
              </span>
            )}
            {scope.kind === 'ready' && (
              <>
                <span>
                  Solo en <strong>{scope.filename}</strong>
                </span>
                <span>
                  <label htmlFor="page">Página</label>{' '}
                  <input
                    id="page"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    placeholder="todas"
                    value={page}
                    aria-invalid={!validPage}
                    onChange={(event) => setPage(event.target.value)}
                  />
                </span>
              </>
            )}
            <a href={routes.ask}>Preguntar a todos los documentos</a>
          </div>
        )}
        <form onSubmit={onSubmit}>
          <label htmlFor="question">Pregunta</label>
          <textarea
            id="question"
            rows={3}
            maxLength={MAX_QUESTION_CHARS}
            value={question}
            placeholder={
              documentId ? 'Ej.: ¿En qué año fue esto?' : 'Ej.: ¿Cuántos días de vacaciones tengo?'
            }
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              // Enter envía; Mayús+Enter añade una línea.
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
          />
          <div className="form-footer">
            <span className="hint">
              {question.length}/{MAX_QUESTION_CHARS}
            </span>
            <button
              type="submit"
              disabled={loading || !question.trim() || !validPage || scopeBlocked}
            >
              {loading ? 'Buscando…' : 'Preguntar'}
            </button>
          </div>
        </form>
      </section>

      <div aria-live="polite">
        {loading && <p className="info">Buscando en los documentos y redactando la respuesta…</p>}
        {state.kind === 'error' && (
          <p className="error" role="alert">
            {state.message}
          </p>
        )}
        {state.kind === 'answered' && <Answer response={state.response} />}
      </div>
    </>
  )
}

function Answer({ response }: { response: QueryResponse }) {
  if (response.insufficient_evidence) {
    return (
      <section className="card notice" aria-label="Respuesta">
        <h3>Sin evidencia suficiente</h3>
        <p>{response.answer}</p>
        <p className="hint">
          Prueba a reformular la pregunta o sube documentos que contengan esa información.
        </p>
      </section>
    )
  }

  return (
    <section className="card" aria-label="Respuesta">
      <h3>Respuesta</h3>
      {/*
        Seguridad: la respuesta la genera un LLM a partir de documentos que podrían ser
        maliciosos. Se muestra como TEXTO (React escapa el contenido); nunca con
        dangerouslySetInnerHTML ni interpretando Markdown, que permitirían inyectar HTML,
        scripts o enlaces/imágenes que filtren datos a un servidor externo.
      */}
      <p className="answer">{response.answer}</p>

      <h4>Fuentes</h4>
      <ol className="sources">
        {response.sources.map((source) => (
          <li key={source.chunk_id ?? `summary-${source.document_id}`}>
            <a href={routes.document(source.document_id)}>{source.filename}</a>
            {source.source_type === 'summary' ? (
              <span>, resumen del documento</span>
            ) : (
              source.page_number !== null && (
                <span>
                  ,{' '}
                  <a
                    href={documentFileUrl(source.document_id, source.page_number)}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Abrir ${source.filename} en la página ${source.page_number}`}
                  >
                    página {source.page_number}
                  </a>
                </span>
              )
            )}
            <blockquote>{source.excerpt}</blockquote>
          </li>
        ))}
      </ol>
    </section>
  )
}

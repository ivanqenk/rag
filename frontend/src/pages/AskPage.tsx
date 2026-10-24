import { useState, type FormEvent } from 'react'
import { ApiError, askQuestion } from '../api/client'
import { routes } from '../router'
import type { QueryResponse } from '../types/api'

// Debe coincidir con MAX_QUERY_CHARS del backend.
const MAX_QUESTION_CHARS = 1000

type AskState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'answered'; response: QueryResponse }
  | { kind: 'error'; message: string }

export function AskPage() {
  const [question, setQuestion] = useState('')
  const [state, setState] = useState<AskState>({ kind: 'idle' })

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'answered', response: await askQuestion(trimmed) })
    } catch (error) {
      setState({
        kind: 'error',
        message: error instanceof ApiError ? error.message : 'No se pudo obtener una respuesta.',
      })
    }
  }

  const loading = state.kind === 'loading'

  return (
    <>
      <section className="card" aria-labelledby="ask-title">
        <h2 id="ask-title">Preguntar a tus documentos</h2>
        <form onSubmit={onSubmit}>
          <label htmlFor="question">Pregunta</label>
          <textarea
            id="question"
            rows={3}
            maxLength={MAX_QUESTION_CHARS}
            value={question}
            placeholder="Ej.: ¿Cuántos días de vacaciones tengo?"
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
            <button type="submit" disabled={loading || !question.trim()}>
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
              source.page_number !== null && <span>, página {source.page_number}</span>
            )}
            <blockquote>{source.excerpt}</blockquote>
          </li>
        ))}
      </ol>
    </section>
  )
}

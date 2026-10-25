import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  askQuestion,
  documentFileUrl,
  getDocument,
  listFolders,
  type HistoryTurn,
} from '../api/client'
import { Icon } from '../components/Icon'
import { routes } from '../router'
import type { AnswerStyle, Folder, QueryResponse } from '../types/api'

const STYLES: Array<{ value: AnswerStyle; label: string; hint: string }> = [
  { value: 'brief', label: 'Breve', hint: 'Una o dos frases' },
  {
    value: 'detailed',
    label: 'Detallada',
    hint: 'Resumen y puntos clave (numerados si el documento describe un procedimiento)',
  },
]

// Turnos anteriores que se envían para entender preguntas de seguimiento (el backend acepta 3).
const HISTORY_TURNS = 3

interface Turn {
  question: string
  response: QueryResponse
}

/** El texto de una respuesta tal como se resume para la conversación. */
function answerText(response: QueryResponse): string {
  return [response.answer, ...response.points.map((point) => point.text)]
    .filter(Boolean)
    .join(' ')
    .slice(0, 4000)
}

// Debe coincidir con MAX_QUERY_CHARS del backend.
const MAX_QUESTION_CHARS = 1000

type AskState = { kind: 'idle' } | { kind: 'loading' } | { kind: 'error'; message: string }

// Pregunta limitada a un documento (desde su página de detalle): solo hace falta su nombre.
type ScopeState =
  | { kind: 'loading' }
  | { kind: 'ready'; filename: string }
  | { kind: 'error'; message: string }

/**
 * Con `documentId` pregunta solo a ese documento (y opcionalmente a una página). Si no, deja
 * elegir entre todos los documentos y una carpeta (`folderId` la preselecciona).
 */
export function AskPage({ documentId, folderId }: { documentId?: string; folderId?: string }) {
  const [question, setQuestion] = useState('')
  const [page, setPage] = useState('')
  const [style, setStyle] = useState<AnswerStyle>('brief')
  const [state, setState] = useState<AskState>({ kind: 'idle' })
  // La conversación vive solo en el navegador: el servidor no guarda preguntas.
  const [turns, setTurns] = useState<Turn[]>([])
  const lastTurn = useRef<HTMLDivElement>(null)

  // Al llegar una respuesta nueva, se lleva a la vista (scrollIntoView no existe en jsdom).
  useEffect(() => {
    lastTurn.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }, [turns.length])
  const [scope, setScope] = useState<ScopeState>({ kind: 'loading' })
  const [folders, setFolders] = useState<Folder[] | null>(null)
  const [selectedFolder, setSelectedFolder] = useState(folderId ?? '')

  useEffect(() => {
    if (documentId) return
    let cancelled = false
    listFolders()
      .then((items) => !cancelled && setFolders(items))
      // Sin carpetas se puede seguir preguntando a todos los documentos.
      .catch(() => !cancelled && setFolders([]))
    return () => {
      cancelled = true
    }
  }, [documentId])

  const missingFolder =
    folders !== null && selectedFolder !== '' && !folders.some((f) => f.id === selectedFolder)

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
        documentId
          ? { documentId, pageNumber: page ? pageNumber : undefined }
          : selectedFolder
            ? { folderId: selectedFolder }
            : undefined,
        style,
        turns.slice(-HISTORY_TURNS).map(
          (turn): HistoryTurn => ({ question: turn.question, answer: answerText(turn.response) }),
        ),
      )
      setTurns((previous) => [...previous, { question: trimmed, response }])
      setQuestion('')
      setState({ kind: 'idle' })
    } catch (error) {
      setState({
        kind: 'error',
        message: error instanceof ApiError ? error.message : 'No se pudo obtener una respuesta.',
      })
    }
  }

  const loading = state.kind === 'loading'
  const scopeBlocked = (documentId !== undefined && scope.kind !== 'ready') || missingFolder

  return (
    <div className="narrow">
      <section className="card" aria-labelledby="ask-title">
        <h2 id="ask-title">
          <Icon name="ask" />
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
        {!documentId && folders !== null && folders.length > 0 && (
          <div className="scope">
            <label htmlFor="folder">Buscar en</label>
            <select
              id="folder"
              value={selectedFolder}
              onChange={(event) => setSelectedFolder(event.target.value)}
            >
              <option value="">Todos los documentos</option>
              {folders.map((folder) => (
                <option key={folder.id} value={folder.id}>
                  {folder.name} ({folder.document_count})
                </option>
              ))}
              {missingFolder && <option value={selectedFolder}>Carpeta desconocida</option>}
            </select>
          </div>
        )}
        {missingFolder && (
          <p className="error" role="alert">
            La carpeta no existe. Elige otra o pregunta a todos los documentos.
          </p>
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
          <fieldset className="segmented">
            <legend>Tipo de respuesta</legend>
            {STYLES.map((option) => (
              <label key={option.value} title={option.hint}>
                <input
                  type="radio"
                  name="answer-style"
                  value={option.value}
                  checked={style === option.value}
                  onChange={() => setStyle(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </fieldset>
          <div className="form-footer">
            <span className="hint">
              {question.length}/{MAX_QUESTION_CHARS}
              {turns.length > 0 && ' · Puedes hacer preguntas de seguimiento («¿y después?»)'}
            </span>
            {turns.length > 0 && (
              <button
                type="button"
                className="secondary"
                disabled={loading}
                onClick={() => {
                  setTurns([])
                  setState({ kind: 'idle' })
                }}
              >
                <Icon name="plus" size={16} />
                Nueva conversación
              </button>
            )}
            <button
              type="submit"
              disabled={loading || !question.trim() || !validPage || scopeBlocked}
            >
              <Icon name="search" size={16} />
              {loading ? 'Buscando…' : 'Preguntar'}
            </button>
          </div>
        </form>
      </section>

      <div aria-live="polite" className="conversation">
        {turns.map((turn, index) => (
          <div
            key={index}
            className="turn"
            ref={index === turns.length - 1 ? lastTurn : undefined}
          >
            <p className="turn-question">
              <Icon name="ask" size={16} />
              <span>{turn.question}</span>
            </p>
            {turn.response.standalone_question && (
              <p className="hint turn-standalone">
                Entendida como: «{turn.response.standalone_question}»
              </p>
            )}
            <Answer response={turn.response} />
          </div>
        ))}
        {loading && <p className="info">Buscando en los documentos y redactando la respuesta…</p>}
        {state.kind === 'error' && (
          <p className="error" role="alert">
            {state.message}
          </p>
        )}
      </div>
    </div>
  )
}

function Answer({ response }: { response: QueryResponse }) {
  if (response.insufficient_evidence) {
    return (
      <section className="card notice" aria-label="Respuesta">
        <h3>
          <Icon name="alert" />
          Sin evidencia suficiente
        </h3>
        <p>{response.answer}</p>
        <p className="hint">
          Prueba a reformular la pregunta o sube documentos que contengan esa información.
        </p>
      </section>
    )
  }

  return (
    <section className="card answer-card" aria-label="Respuesta">
      <h3>
        <Icon name="sparkles" />
        Respuesta
      </h3>
      {/*
        Seguridad: la respuesta la genera un LLM a partir de documentos que podrían ser
        maliciosos. Se muestra como TEXTO (React escapa el contenido); nunca con
        dangerouslySetInnerHTML ni interpretando Markdown, que permitirían inyectar HTML,
        scripts o enlaces/imágenes que filtren datos a un servidor externo.
      */}
      {response.answer && <p className="answer">{response.answer}</p>}
      {response.points.length > 0 && <Points response={response} />}
      {response.answer_style !== 'brief' && (
        <p className="hint verified">
          <Icon name="search" size={14} />
          Cada punto se ha comprobado contra el texto de sus fuentes; lo que no estaba respaldado
          se ha descartado.
        </p>
      )}

      <h4 className="sources-title">Fuentes</h4>
      <ol className="sources">
        {response.sources.map((source) => (
          <li key={source.chunk_id ?? `summary-${source.document_id}`}>
            <div className="source-head">
              <a href={routes.document(source.document_id)}>{source.filename}</a>
              {source.source_type === 'summary' ? (
                <span className="page-chip">Resumen del documento</span>
              ) : (
                source.page_number !== null && (
                  <a
                    className="page-chip"
                    href={documentFileUrl(source.document_id, source.page_number)}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Abrir ${source.filename} en la página ${source.page_number}`}
                  >
                    página {source.page_number}
                    <Icon name="external" size={13} />
                  </a>
                )
              )}
            </div>
            <blockquote>{source.excerpt}</blockquote>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** Puntos o pasos, cada uno con enlaces a sus fuentes (el número coincide con «Fuentes»). */
function Points({ response }: { response: QueryResponse }) {
  const List = response.points_ordered ? 'ol' : 'ul'
  return (
    <List className={`points${response.points_ordered ? ' points-ordered' : ''}`}>
      {response.points.map((point, index) => (
        <li key={index}>
          <span>{point.text}</span>{' '}
          {point.sources.map((sourceIndex) => {
            const source = response.sources[sourceIndex]
            if (!source) return null
            const where = source.page_number ? `, página ${source.page_number}` : ''
            return (
              <a
                key={sourceIndex}
                className="cite"
                href={
                  source.page_number
                    ? documentFileUrl(source.document_id, source.page_number)
                    : routes.document(source.document_id)
                }
                target={source.page_number ? '_blank' : undefined}
                rel={source.page_number ? 'noopener noreferrer' : undefined}
                aria-label={`Fuente ${sourceIndex + 1}: ${source.filename}${where}`}
                title={`${source.filename}${where}`}
              >
                {sourceIndex + 1}
              </a>
            )
          })}
        </li>
      ))}
    </List>
  )
}

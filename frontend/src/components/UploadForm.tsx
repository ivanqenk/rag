import { useRef, useState, type DragEvent } from 'react'
import { ApiError, uploadDocument } from '../api/client'
import { MAX_UPLOAD_MB } from '../config'
import type { DocumentRead, Folder } from '../types/api'
import { validateFile } from '../validation'
import { Icon } from './Icon'

type UploadState =
  | { kind: 'idle' }
  | { kind: 'uploading'; filename: string }
  | { kind: 'done'; document: DocumentRead }
  | { kind: 'error'; message: string }

/** Sube un PDF; con `folder`, lo guarda en esa carpeta. */
export function UploadForm({ folder, onUploaded }: { folder?: Folder; onUploaded: () => void }) {
  const [state, setState] = useState<UploadState>({ kind: 'idle' })
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    const problem = validateFile(file)
    if (problem) {
      setState({ kind: 'error', message: problem })
      return
    }
    setState({ kind: 'uploading', filename: file.name })
    try {
      const document = await uploadDocument(file, folder?.id)
      setState({ kind: 'done', document })
      onUploaded()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'No se pudo subir el archivo.'
      setState({ kind: 'error', message })
    } finally {
      // Permite volver a elegir el mismo archivo.
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) void handleFile(file)
  }

  const uploading = state.kind === 'uploading'

  return (
    <section className="card" aria-labelledby="upload-title">
      <h2 id="upload-title">
        <Icon name="upload" />
        Subir documento
      </h2>
      {/* El <label> envuelve el input: es clicable, accesible por teclado y acepta arrastrar. */}
      <label
        className={`dropzone${dragging ? ' dropzone-active' : ''}${uploading ? ' dropzone-busy' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="visually-hidden-input"
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void handleFile(file)
          }}
        />
        <span className="dropzone-icon">
          <Icon name="upload" size={22} />
        </span>
        <span className="dropzone-text">
          Arrastra un PDF aquí o <span className="link-like">elige un archivo</span>
        </span>
        <span className="hint">Máximo {MAX_UPLOAD_MB} MB. PDF con texto (los escaneados no son compatibles).</span>
        {folder && <span className="hint">Se guardará en «{folder.name}».</span>}
      </label>

      {/* aria-live anuncia los cambios de estado a los lectores de pantalla. */}
      <div aria-live="polite" className="status-area">
        {state.kind === 'uploading' && (
          <p className="info">Subiendo y procesando «{state.filename}»… puede tardar unos segundos.</p>
        )}
        {state.kind === 'done' && state.document.status === 'completed' && (
          <p className="success">«{state.document.original_filename}» está listo para consultas.</p>
        )}
        {state.kind === 'done' && state.document.status === 'failed' && (
          <p className="error">
            «{state.document.original_filename}» se subió, pero no se pudo procesar:{' '}
            {state.document.error_message}
          </p>
        )}
        {state.kind === 'error' && (
          <p className="error" role="alert">
            {state.message}
          </p>
        )}
      </div>
    </section>
  )
}

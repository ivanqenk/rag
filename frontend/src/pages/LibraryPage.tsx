import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  createFolder,
  deleteDocument,
  deleteFolder,
  listDocuments,
  listFolders,
  moveDocument,
  renameFolder,
  reprocessDocument,
} from '../api/client'
import { Icon } from '../components/Icon'
import { StatusBadge } from '../components/StatusBadge'
import { UploadForm } from '../components/UploadForm'
import { formatBytes, formatDate } from '../format'
import { routes } from '../router'
import type { DocumentRead, Folder } from '../types/api'
import { isProcessing, usePolling } from '../usePolling'

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; documents: DocumentRead[]; total: number; folders: Folder[] }

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

async function fetchListState(folderId?: string): Promise<ListState> {
  try {
    const [page, folders] = await Promise.all([listDocuments(50, 0, folderId), listFolders()])
    return { kind: 'ready', documents: page.items, total: page.total, folders }
  } catch (error) {
    return { kind: 'error', message: errorText(error, 'No se pudo cargar la biblioteca.') }
  }
}

/** Biblioteca: todos los documentos o, con `folderId`, solo los de esa carpeta. */
export function LibraryPage({ folderId }: { folderId?: string }) {
  const [state, setState] = useState<ListState>({ kind: 'loading' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => setState(await fetchListState(folderId)), [folderId])

  useEffect(() => {
    let cancelled = false
    void fetchListState(folderId).then((next) => !cancelled && setState(next))
    return () => {
      cancelled = true
    }
  }, [folderId])

  // Mientras algún documento se procesa en segundo plano, la lista se actualiza sola.
  const anyProcessing =
    state.kind === 'ready' && state.documents.some((document) => isProcessing(document.status))
  usePolling(() => void load(), anyProcessing, 3000)

  async function runAction(id: string, action: () => Promise<unknown>): Promise<boolean> {
    setActionError(null)
    setBusyId(id)
    try {
      await action()
      await load()
      return true
    } catch (error) {
      setActionError(errorText(error, 'La operación no se completó.'))
      return false
    } finally {
      setBusyId(null)
    }
  }

  function onDelete(document: DocumentRead) {
    const confirmed = window.confirm(
      `¿Eliminar «${document.original_filename}»? Irá a la papelera: podrás restaurarlo ` +
        'durante 30 días; después se borrará definitivamente.',
    )
    if (confirmed) void runAction(document.id, () => deleteDocument(document.id))
  }

  const folders = state.kind === 'ready' ? state.folders : []
  const current = folders.find((folder) => folder.id === folderId)
  const unknownFolder = state.kind === 'ready' && folderId !== undefined && !current

  return (
    <div className="library-layout">
      <aside className="library-aside">
        <FolderBar
          folders={folders}
          current={current}
          busy={busyId !== null}
          onAction={(action) => runAction('folders', action)}
        />
      </aside>

      <div className="library-main">
        {unknownFolder ? (
          <section className="card">
            <p className="error" role="alert">
              La carpeta no existe.
            </p>
            <a href={routes.library}>Ver todos los documentos</a>
          </section>
        ) : (
          <UploadForm folder={current} onUploaded={() => void load()} />
        )}

        <section className="card" aria-labelledby="library-title">
          <div className="card-header">
            <h2 id="library-title">
              <Icon name={current ? 'folder' : 'library'} />
              {current ? current.name : 'Biblioteca'}
            </h2>
            {state.kind === 'ready' && (
              <span className="hint">
                {state.total} documento{state.total === 1 ? '' : 's'}
              </span>
            )}
          </div>
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
            <p className="empty">
              <Icon name="file" size={36} />
              {current
                ? 'Esta carpeta está vacía. Sube un PDF o mueve aquí un documento.'
                : 'Aún no hay documentos. Sube un PDF para empezar.'}
            </p>
          )}
          {state.kind === 'ready' && state.documents.length > 0 && (
            <>
              <div className="table-wrap">
                <table>
                  <caption className="visually-hidden">
                    {state.total} documento{state.total === 1 ? '' : 's'}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Nombre</th>
                      <th scope="col">Carpeta</th>
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
                        <td className="name">
                          <a href={routes.document(document.id)}>
                            <Icon name="file" />
                            {document.original_filename}
                          </a>
                          {document.status === 'failed' && document.error_message && (
                            <div className="row-error">{document.error_message}</div>
                          )}
                        </td>
                        <td data-label="Carpeta">
                          <select
                            aria-label={`Carpeta de ${document.original_filename}`}
                            value={document.folder_id ?? ''}
                            disabled={busyId === document.id}
                            onChange={(event) => {
                              const target = event.target.value || null
                              void runAction(document.id, () => moveDocument(document.id, target))
                            }}
                          >
                            <option value="">Sin carpeta</option>
                            {state.folders.map((folder) => (
                              <option key={folder.id} value={folder.id}>
                                {folder.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="muted" data-label="Tamaño">
                          {formatBytes(document.size_bytes)}
                        </td>
                        <td className="muted" data-label="Subido">
                          {formatDate(document.created_at)}
                        </td>
                        <td data-label="Estado">
                          <StatusBadge status={document.status} />
                        </td>
                        <td className="actions">
                          {document.status === 'failed' && (
                            <button
                              type="button"
                              className="secondary small"
                              aria-label="Reintentar"
                              title="Reintentar"
                              disabled={busyId === document.id}
                              onClick={() =>
                                void runAction(document.id, () => reprocessDocument(document.id))
                              }
                            >
                              <Icon name="refresh" size={16} />
                              <span className="btn-label">Reintentar</span>
                            </button>
                          )}
                          <button
                            type="button"
                            className="danger small"
                            disabled={busyId === document.id}
                            aria-label={`Eliminar ${document.original_filename}`}
                            title="Eliminar"
                            onClick={() => onDelete(document)}
                          >
                            <Icon name="trash" size={16} />
                            <span className="btn-label">Eliminar</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {state.total > state.documents.length && (
                <p className="hint">
                  Mostrando {state.documents.length} de {state.total} documentos.
                </p>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}

function FolderBar({
  folders,
  current,
  busy,
  onAction,
}: {
  folders: Folder[]
  current: Folder | undefined
  busy: boolean
  onAction: (action: () => Promise<unknown>) => Promise<boolean>
}) {
  const [name, setName] = useState('')

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    if (await onAction(() => createFolder(trimmed))) setName('')
  }

  function onRename(folder: Folder) {
    const next = window.prompt('Nuevo nombre de la carpeta', folder.name)?.trim()
    if (next && next !== folder.name) void onAction(() => renameFolder(folder.id, next))
  }

  function onDelete(folder: Folder) {
    const confirmed = window.confirm(
      `¿Eliminar la carpeta «${folder.name}»? Sus documentos no se borran: quedarán sin carpeta.`,
    )
    if (!confirmed) return
    void onAction(async () => {
      await deleteFolder(folder.id)
      window.location.hash = routes.library
    })
  }

  return (
    <section className="card" aria-labelledby="folders-title">
      <h2 id="folders-title">
        <Icon name="folder" />
        Carpetas
      </h2>
      <nav aria-label="Carpetas" className="folders">
        <a href={routes.library} aria-current={current ? undefined : 'page'}>
          <Icon name="library" />
          <span className="folder-name">Todos</span>
        </a>
        {folders.map((folder) => (
          <a
            key={folder.id}
            href={routes.folder(folder.id)}
            aria-current={folder.id === current?.id ? 'page' : undefined}
          >
            <Icon name="folder" />
            <span className="folder-name">{folder.name}</span>{' '}
            <span className="count">{folder.document_count}</span>
          </a>
        ))}
      </nav>
      {current && (
        <div className="folder-actions">
          <a href={routes.askFolder(current.id)}>
            <Icon name="ask" size={16} />
            Preguntar a esta carpeta
          </a>
          <button type="button" className="link-button" onClick={() => onRename(current)}>
            <Icon name="pencil" size={16} />
            Renombrar
          </button>
          <button type="button" className="link-button danger" onClick={() => onDelete(current)}>
            <Icon name="trash" size={16} />
            Eliminar carpeta
          </button>
        </div>
      )}
      <form className="inline-form" onSubmit={onCreate}>
        <label htmlFor="folder-name" className="visually-hidden">
          Nombre de la nueva carpeta
        </label>
        <input
          id="folder-name"
          type="text"
          maxLength={100}
          placeholder="Nueva carpeta"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button
          type="submit"
          aria-label="Crear carpeta"
          title="Crear carpeta"
          disabled={busy || !name.trim()}
        >
          <Icon name="plus" />
        </button>
      </form>
    </section>
  )
}

import { Icon } from './components/Icon'
import { ThemeToggle } from './components/ThemeToggle'
import { UsageBar } from './components/UsageBar'
import { AskPage } from './pages/AskPage'
import { DocumentPage } from './pages/DocumentPage'
import { LibraryPage } from './pages/LibraryPage'
import { TrashPage } from './pages/TrashPage'
import { routes, useRoute } from './router'

export default function App() {
  const route = useRoute()

  return (
    <>
      <header className="app-header">
        <div className="header-inner">
          <h1 className="brand">
            <span className="brand-mark">
              <Icon name="sparkles" size={20} />
            </span>
            <span>
              Document Intelligence
              <small>Pregunta a tus documentos</small>
            </span>
          </h1>
          <nav aria-label="Principal" className="main-nav">
            <a
              href={routes.library}
              aria-current={
                route.name === 'library' || route.name === 'document' ? 'page' : undefined
              }
            >
              <Icon name="library" />
              Biblioteca
            </a>
            <a href={routes.ask} aria-current={route.name === 'ask' ? 'page' : undefined}>
              <Icon name="ask" />
              Preguntar
            </a>
            <a href={routes.trash} aria-current={route.name === 'trash' ? 'page' : undefined}>
              <Icon name="trash" />
              Papelera
            </a>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main>
        {route.name === 'library' && (
          <LibraryPage key={route.folderId ?? 'todas'} folderId={route.folderId} />
        )}
        {route.name === 'ask' && (
          <AskPage
            key={route.documentId ?? route.folderId ?? 'todos'}
            documentId={route.documentId}
            folderId={route.folderId}
          />
        )}
        {route.name === 'trash' && <TrashPage />}
        {route.name === 'document' && <DocumentPage key={route.id} id={route.id} />}
      </main>
      <footer className="app-footer">
        <UsageBar refreshKey={window.location.hash} />
        Demo de portafolio de un solo usuario: no es un servicio listo para producción.
      </footer>
    </>
  )
}

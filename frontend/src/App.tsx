import { AskPage } from './pages/AskPage'
import { DocumentPage } from './pages/DocumentPage'
import { LibraryPage } from './pages/LibraryPage'
import { routes, useRoute } from './router'

export default function App() {
  const route = useRoute()

  return (
    <>
      <header className="app-header">
        <h1>Document Intelligence</h1>
        <nav aria-label="Principal">
          <a href={routes.library} aria-current={route.name !== 'ask' ? 'page' : undefined}>
            Biblioteca
          </a>
          <a href={routes.ask} aria-current={route.name === 'ask' ? 'page' : undefined}>
            Preguntar
          </a>
        </nav>
      </header>
      <main>
        {route.name === 'library' && <LibraryPage />}
        {route.name === 'ask' && <AskPage />}
        {route.name === 'document' && <DocumentPage key={route.id} id={route.id} />}
      </main>
      <footer className="app-footer">
        Demo de portafolio de un solo usuario: no es un servicio listo para producción.
      </footer>
    </>
  )
}

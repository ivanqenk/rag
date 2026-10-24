import { vi } from 'vitest'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Sustituye fetch por una función que devuelve las respuestas indicadas, en orden. */
export function mockFetch(...responses: Array<Response | Error>) {
  const spy = vi.spyOn(globalThis, 'fetch')
  for (const response of responses) {
    if (response instanceof Error) spy.mockRejectedValueOnce(response)
    else spy.mockResolvedValueOnce(response)
  }
  return spy
}

type Reply = Response | Error

/**
 * Sustituye fetch por un servidor simulado que responde según "MÉTODO /ruta" (sin la query).
 * Con una lista, cada llamada consume la siguiente respuesta y la última se repite. Útil
 * cuando una pantalla hace varias peticiones en paralelo y el orden no está garantizado.
 * Las respuestas se clonan: el mismo cuerpo se puede leer en varias llamadas.
 */
export function mockApi(routes: Record<string, Reply | Reply[]>) {
  const queues = new Map(
    Object.entries(routes).map(([key, value]) => [key, Array.isArray(value) ? [...value] : [value]]),
  )
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const key = `${init?.method ?? 'GET'} ${url.pathname}`
    const queue = queues.get(key)
    if (!queue) throw new Error(`Petición no simulada: ${key}`)
    const reply = queue.length > 1 ? queue.shift()! : queue[0]
    if (reply instanceof Error) throw reply
    return reply.clone()
  })
}

/** Las peticiones hechas a fetch como "MÉTODO /ruta?query". */
export function requests(spy: ReturnType<typeof mockApi>): string[] {
  return spy.mock.calls.map(([input, init]) => {
    const url = new URL(String(input), 'http://localhost')
    return `${init?.method ?? 'GET'} ${url.pathname}${url.search}`
  })
}

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

import { describe, expect, it } from 'vitest'
import { validateFile } from './validation'

const file = (name: string, size: number) => new File([new Uint8Array(size)], name)

describe('validateFile', () => {
  it('acepta un PDF de tamaño razonable', () => {
    expect(validateFile(file('Informe.PDF', 100))).toBeNull()
  })

  it.each([
    [file('notas.txt', 100), 'Solo se admiten archivos PDF.'],
    [file('vacio.pdf', 0), 'El archivo está vacío.'],
    [file('grande.pdf', 21 * 1024 * 1024), 'El archivo supera el máximo de 20 MB.'],
  ])('rechaza %s', (input, message) => {
    expect(validateFile(input)).toBe(message)
  })
})

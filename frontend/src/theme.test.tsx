import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeToggle } from './components/ThemeToggle'
import { applyTheme, storedTheme } from './theme'

describe('tema', () => {
  afterEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('es claro por defecto', () => {
    expect(storedTheme()).toBe('light')
  })

  it('cambia a oscuro, lo aplica y lo recuerda', async () => {
    applyTheme(storedTheme())
    render(<ThemeToggle />)

    await userEvent.click(screen.getByRole('button', { name: 'Tema oscuro' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('tema')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Tema oscuro' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Tema claro' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('funciona aunque el navegador bloquee el almacenamiento', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    render(<ThemeToggle />)

    await userEvent.click(screen.getByRole('button', { name: 'Tema oscuro' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})

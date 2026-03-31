import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Locale } from './i18n'

interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

export type Theme = 'light' | 'dark'

interface AppStore {
  projectPath: string
  theme: Theme
  locale: Locale
  toasts: Toast[]
  setProjectPath: (path: string) => void
  setTheme: (theme: Theme) => void
  setLocale: (locale: Locale) => void
  toast: (type: Toast['type'], message: string) => void
  dismissToast: (id: string) => void
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      projectPath: '',
      theme: 'dark',
      locale: 'en',
      toasts: [],
      setProjectPath: (path) => set({ projectPath: path }),
      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme)
        set({ theme })
      },
      setLocale: (locale) => set({ locale }),
      toast: (type, message) => {
        const id = Math.random().toString(36).slice(2)
        set(state => ({ toasts: [...state.toasts, { id, type, message }] }))
        setTimeout(() => set(state => ({ toasts: state.toasts.filter(t => t.id !== id) })), 4000)
      },
      dismissToast: (id) => set(state => ({ toasts: state.toasts.filter(t => t.id !== id) })),
    }),
    {
      name: 'archmap-store',
      partialize: (s) => ({ projectPath: s.projectPath, theme: s.theme, locale: s.locale }),
    }
  )
)

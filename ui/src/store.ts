import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ProjectStatus } from './types'

interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

interface AppStore {
  projectPath: string
  projectStatus: ProjectStatus | null
  toasts: Toast[]
  setProjectPath: (path: string) => void
  setProjectStatus: (s: ProjectStatus | null) => void
  toast: (type: Toast['type'], message: string) => void
  dismissToast: (id: string) => void
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      projectPath: '',
      projectStatus: null,
      toasts: [],

      setProjectPath: (path) => set({ projectPath: path, projectStatus: null }),

      setProjectStatus: (s) => set({ projectStatus: s }),

      toast: (type, message) => {
        const id = Math.random().toString(36).slice(2)
        set(state => ({ toasts: [...state.toasts, { id, type, message }] }))
        setTimeout(() => set(state => ({ toasts: state.toasts.filter(t => t.id !== id) })), 4000)
      },

      dismissToast: (id) => set(state => ({ toasts: state.toasts.filter(t => t.id !== id) })),
    }),
    { name: 'archmap-store', partialize: (s) => ({ projectPath: s.projectPath }) }
  )
)

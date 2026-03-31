# ArchMap v2 UI

React + Vite frontend for the purpose tree. Minimal stack: react, react-dom, zustand.

## Structure

```
ui/src/
  App.tsx            Main UI — collapsible tree + task panel
  api/archMapApi.ts  Fetch wrapper for all API endpoints
  types.ts           TypeScript types (TreeNode, Task, ProjectStatus)
  store.ts           Zustand store (projectPath + toasts)
  main.tsx           Entry point
```

## Running

```bash
cd ui && npm run dev   # port 5174
```

API server must be running on port 8765. Proxy configured in vite.config.ts.

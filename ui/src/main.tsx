import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { useStore } from './store'

// Apply persisted theme on load
const theme = useStore.getState().theme
document.documentElement.setAttribute('data-theme', theme)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

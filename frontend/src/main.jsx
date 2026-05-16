import React from 'react'
import ReactDOM from 'react-dom/client'
import * as Sentry from '@sentry/react'
import App from './App'
import './styles/index.css'

// WHY conditional init: VITE_SENTRY_DSN is empty in local dev by default.
// Calling Sentry.init() with no DSN would log a console warning on every
// page load — skip entirely when the DSN is not configured.
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    // WHY 0.1 sample rate: captures 10% of sessions as performance traces.
    // Full capture (1.0) burns through the free-tier quota quickly.
    tracesSampleRate: 0.1,
    environment: import.meta.env.MODE,  // "development" or "production"
  })
}

// WHY: React 18 replaces ReactDOM.render with createRoot — this enables
// concurrent rendering features (transitions, Suspense boundaries, etc.)
// StrictMode double-invokes renders in dev to surface side-effect bugs
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

// frontend/src/api/client.js
import axios from 'axios'

// WHY fallback to '/api': in local dev VITE_API_BASE_URL is unset.
// Vite's proxy rewrites /api/* → http://localhost:8000/* so requests
// appear same-origin and avoid CORS preflights during development.
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export default axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 20_000,
})

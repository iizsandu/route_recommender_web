// frontend/src/hooks/useRouteRecommend.js
import { useState } from 'react'
import client from '../api/client'

export function useRouteRecommend() {
  const [routes, setRoutes]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function recommend({ origin, destination, depart_time }) {
    setLoading(true)
    setError(null)
    try {
      const { data } = await client.post('/routes/recommend', {
        origin,
        destination,
        depart_time,
      })
      setRoutes(data.routes)
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Could not fetch routes. Try again.')
      setRoutes([])
    } finally {
      setLoading(false)
    }
  }

  return { routes, loading, error, recommend }
}

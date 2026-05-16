// frontend/src/App.jsx
import { useState } from 'react'
import { useRouteRecommend } from './hooks/useRouteRecommend'
import DisclaimerModal, { hasAcknowledged } from './components/DisclaimerModal'
import RouteForm from './components/RouteForm'
import RouteResults from './components/RouteResults'
import MapView from './components/MapView'

export default function App() {
  const [disclaimerOpen, setDisclaimerOpen] = useState(!hasAcknowledged())
  const [selectedIdx, setSelectedIdx]       = useState(0)

  const { routes, loading, error, recommend } = useRouteRecommend()

  async function handleFormSubmit(params) {
    setSelectedIdx(0)
    await recommend(params)
  }

  return (
    <div className="flex flex-col h-screen">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-3 bg-white border-b shadow-sm z-10">
        <span className="font-semibold text-gray-800 text-sm">
          Route Recommender — Delhi NCR
        </span>
        <button
          onClick={() => setDisclaimerOpen(true)}
          className="text-gray-400 hover:text-gray-600 text-lg leading-none"
          title="About this app"
          aria-label="Open disclaimer"
        >
          ⓘ
        </button>
      </header>

      {/* ── Main layout ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <aside className="w-80 shrink-0 bg-white border-r overflow-y-auto p-4 space-y-4">
          <RouteForm onSubmit={handleFormSubmit} loading={loading} />

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <RouteResults
            routes={routes}
            selectedIdx={selectedIdx}
            onSelect={setSelectedIdx}
          />
        </aside>

        {/* Map panel */}
        <main className="flex-1">
          <MapView
            routes={routes}
            selectedIdx={selectedIdx}
            onSelectRoute={setSelectedIdx}
          />
        </main>
      </div>

      <DisclaimerModal
        open={disclaimerOpen}
        onClose={() => setDisclaimerOpen(false)}
      />
    </div>
  )
}

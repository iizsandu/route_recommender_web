// frontend/src/components/RouteResults.jsx

const BADGE = {
  Low:    'bg-green-100 text-green-800',
  Medium: 'bg-amber-100 text-amber-800',
  High:   'bg-red-100 text-red-800',
}

function fmtDuration(sec) {
  const m = Math.round(sec / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`
}

function fmtDistance(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

export default function RouteResults({ routes, selectedIdx, onSelect }) {
  if (!routes.length) return null

  return (
    <div className="space-y-2 mt-4">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {routes.length} route{routes.length > 1 ? 's' : ''} found
      </p>

      {routes.map((route, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(i)}
          className={`w-full text-left rounded-xl border p-3 transition-all ${
            selectedIdx === i
              ? 'border-indigo-500 bg-indigo-50 shadow-sm'
              : 'border-gray-200 bg-white hover:border-gray-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-800">
              Route {i + 1}{i === 0 ? ' — Safest' : ''}
            </span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${BADGE[route.risk_band]}`}>
              {route.risk_band}
            </span>
          </div>
          <div className="mt-1 flex gap-3 text-xs text-gray-500">
            <span>{fmtDuration(route.duration_sec)}</span>
            <span>·</span>
            <span>{fmtDistance(route.distance_m)}</span>
          </div>
        </button>
      ))}
    </div>
  )
}

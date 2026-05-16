// frontend/src/components/DisclaimerModal.jsx

const STORAGE_KEY = 'disclaimer_acknowledged_v1'

export function hasAcknowledged() {
  return !!localStorage.getItem(STORAGE_KEY)
}

export default function DisclaimerModal({ open, onClose }) {
  if (!open) return null

  function acknowledge() {
    localStorage.setItem(STORAGE_KEY, '1')
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Safety Information — Please Read
        </h2>

        <div className="text-sm text-gray-600 space-y-2">
          <p>
            Route risk estimates are based on <strong>historical crime news data</strong> extracted
            from public sources. They reflect patterns in reported incidents, not real-time events.
          </p>
          <p>
            Risk bands (Low / Medium / High) are statistical estimates only. They are{' '}
            <strong>not a guarantee of safety</strong> on any route and should not replace your
            personal judgement.
          </p>
          <p>
            Data coverage is limited to Delhi-NCR and may not reflect all areas equally.
            No warranty is provided.
          </p>
        </div>

        <button
          onClick={acknowledge}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2.5 rounded-xl transition-colors"
        >
          I understand — continue
        </button>
      </div>
    </div>
  )
}

// frontend/src/components/RouteForm.jsx
import { useState } from 'react'
import TimeOfDayPicker from './TimeOfDayPicker'

export default function RouteForm({ onSubmit, loading }) {
  const [origin, setOrigin]           = useState('')
  const [destination, setDestination] = useState('')
  const [departTime, setDepartTime]   = useState(new Date().toISOString())

  function handleSubmit(e) {
    e.preventDefault()
    if (!origin.trim() || !destination.trim()) return
    onSubmit({ origin: origin.trim(), destination: destination.trim(), depart_time: departTime })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          From
        </label>
        <input
          type="text"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="e.g. Connaught Place, Delhi"
          required
          className="mt-1 block w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      </div>

      <div>
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          To
        </label>
        <input
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="e.g. Lajpat Nagar, Delhi"
          required
          className="mt-1 block w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      </div>

      <TimeOfDayPicker value={departTime} onChange={setDepartTime} />

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-medium py-2.5 rounded-xl transition-colors"
      >
        {loading ? 'Finding safest route…' : 'Find safest route'}
      </button>
    </form>
  )
}

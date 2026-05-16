// frontend/src/components/TimeOfDayPicker.jsx
import { useState } from 'react'

const PRESETS = [
  {
    label: 'Now',
    getDate: () => new Date(),
  },
  {
    label: 'This evening',
    getDate: () => {
      const d = new Date()
      d.setHours(18, 0, 0, 0)
      return d
    },
  },
  {
    label: 'Tonight',
    getDate: () => {
      const d = new Date()
      d.setHours(22, 0, 0, 0)
      return d
    },
  },
  {
    label: 'Tomorrow morning',
    getDate: () => {
      const d = new Date()
      d.setDate(d.getDate() + 1)
      d.setHours(8, 0, 0, 0)
      return d
    },
  },
]

export default function TimeOfDayPicker({ value, onChange }) {
  const [activePreset, setActivePreset] = useState('Now')

  function selectPreset(preset) {
    setActivePreset(preset.label)
    onChange(preset.getDate().toISOString())
  }

  function handleCustomTime(e) {
    setActivePreset(null)
    // Combine today's date with the chosen time
    const [h, m] = e.target.value.split(':')
    const d = new Date()
    d.setHours(Number(h), Number(m), 0, 0)
    onChange(d.toISOString())
  }

  return (
    <div className="space-y-2">
      <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Departure time
      </label>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => selectPreset(p)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activePreset === p.label
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <input
        type="time"
        onChange={handleCustomTime}
        className="mt-1 block w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        placeholder="Custom time"
      />
    </div>
  )
}

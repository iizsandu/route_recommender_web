// frontend/src/components/MapView.jsx
import { useEffect, useRef, useState } from 'react'
import Map, { Source, Layer, NavigationControl, GeolocateControl } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'

const BAND_COLOR = {
  Low:    '#22c55e',
  Medium: '#f59e0b',
  High:   '#ef4444',
}

const DELHI_CENTER = { longitude: 77.2090, latitude: 28.6139, zoom: 11 }

const MAP_STYLE = `https://api.maptiler.com/maps/streets/style.json?key=${
  import.meta.env.VITE_MAPTILER_KEY ?? ''
}`

// Geographic bounds of the heatmap PNG — must match LAT/LNG bounds in generate_heatmap.py
// MapLibre image source coordinates: [top-left, top-right, bottom-right, bottom-left] as [lng, lat]
const HEATMAP_BOUNDS = [
  [76.5, 29.5],   // top-left
  [78.0, 29.5],   // top-right
  [78.0, 28.0],   // bottom-right
  [76.5, 28.0],   // bottom-left
]

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const HEATMAP_IMAGE_URL = `${BASE_URL}/risk/heatmap-image`

export default function MapView({ routes, selectedIdx, onSelectRoute }) {
  const mapRef = useRef(null)
  const [showHeatmap, setShowHeatmap] = useState(true)
  // Show immediately — MapLibre silently no-ops if the image 404s/503s.
  const imageLoaded = true
  const imageError  = false

  // Fly to fit the selected route
  useEffect(() => {
    if (!mapRef.current || !routes[selectedIdx]) return
    const coords = routes[selectedIdx].geometry.coordinates
    if (!coords?.length) return
    const lngs = coords.map(c => c[0])
    const lats  = coords.map(c => c[1])
    mapRef.current.fitBounds(
      [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      { padding: 60, duration: 800 },
    )
  }, [selectedIdx, routes])

  return (
    <div className="relative w-full h-full">
      <Map
        ref={mapRef}
        initialViewState={DELHI_CENTER}
        style={{ width: '100%', height: '100%' }}
        mapStyle={MAP_STYLE}
      >
        <NavigationControl position="top-right" />
        <GeolocateControl position="top-right" />

        {/* ── Raster heatmap image (renders below routes) ─────────────── */}
        {imageLoaded && (
          <Source
            id="heatmap-raster"
            type="image"
            url={HEATMAP_IMAGE_URL}
            coordinates={HEATMAP_BOUNDS}
          >
            <Layer
              id="heatmap-raster-layer"
              type="raster"
              paint={{
                // bilinear resampling keeps the gradient smooth when zoomed in
                'raster-resampling': 'linear',
                'raster-opacity': showHeatmap ? [
                  'interpolate', ['linear'], ['zoom'],
                  8,  0.82,
                  13, 0.65,
                  15, 0.25,
                ] : 0,
                'raster-fade-duration': 400,
              }}
            />
          </Source>
        )}

        {/* ── Route polylines (always above heatmap) ───────────────────── */}
        {[...routes].reverse().map((route, revIdx) => {
          const i = routes.length - 1 - revIdx
          const isSelected = i === selectedIdx
          return (
            <Source key={i} id={`route-${i}`} type="geojson" data={route.geometry}>
              <Layer
                id={`route-${i}-hit`}
                type="line"
                paint={{ 'line-width': 20, 'line-opacity': 0 }}
                onClick={() => onSelectRoute(i)}
              />
              <Layer
                id={`route-${i}-line`}
                type="line"
                paint={{
                  'line-color':   BAND_COLOR[route.risk_band],
                  'line-width':   isSelected ? 6 : 3,
                  'line-opacity': isSelected ? 1 : 0.6,
                }}
              />
            </Source>
          )
        })}
      </Map>

      {/* ── Toggle button ─────────────────────────────────────────────── */}
      {!imageError && imageLoaded && (
        <button
          onClick={() => setShowHeatmap(v => !v)}
          className={`absolute top-3 left-3 z-10 flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium shadow-md border transition-all ${
            showHeatmap
              ? 'bg-white border-indigo-300 text-indigo-700'
              : 'bg-white border-gray-200 text-gray-400 hover:text-gray-600'
          }`}
        >
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${showHeatmap ? 'bg-indigo-500' : 'bg-gray-300'}`} />
          Risk heatmap
        </button>
      )}

      {/* ── Legend ───────────────────────────────────────────────────── */}
      {showHeatmap && imageLoaded && (
        <div className="absolute bottom-8 left-3 z-10 bg-white/90 backdrop-blur-sm rounded-xl shadow-md border border-gray-100 px-3 py-2.5 text-xs">
          <p className="font-semibold text-gray-500 mb-2 uppercase tracking-wide" style={{ fontSize: '10px' }}>
            Historical Crime Risk
          </p>
          <div
            className="w-28 h-2.5 rounded-full mb-1"
            style={{ background: 'linear-gradient(to right, rgba(255,220,80,0.4), rgba(255,100,0,0.8), rgba(140,0,0,0.95))' }}
          />
          <div className="flex justify-between text-gray-400 mb-1" style={{ fontSize: '9px' }}>
            <span>Lower</span><span>Higher</span>
          </div>
          <p className="text-gray-300 leading-tight" style={{ fontSize: '9px' }}>
            Transparent = low risk
          </p>
        </div>
      )}

      {/* ── Loading state ────────────────────────────────────────────── */}
      {!imageLoaded && !imageError && (
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-gray-400 bg-white/80 shadow-sm border border-gray-100">
          <span className="w-2 h-2 rounded-full bg-gray-300 animate-pulse" />
          Loading heatmap…
        </div>
      )}
    </div>
  )
}

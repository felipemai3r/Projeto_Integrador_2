import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet'
import { api } from '../../lib/api'
import styles from './MapaBase.module.css'

export const CENTRO: [number, number] = [-27.0455, -49.6243]

/** Base dos mapas: OpenStreetMap, contorno do municipio e quem mais vier como filho. */
export function MapaBase({ children, rotulo }: { children?: ReactNode; rotulo: string }) {
  const [contorno, setContorno] = useState<GeoJSON.FeatureCollection | null>(null)
  useEffect(() => {
    api
      .contorno()
      .then(setContorno)
      .catch(() => setContorno(null))
  }, [])
  return (
    <div className={styles.mapa} role="region" aria-label={rotulo}>
      <MapContainer center={CENTRO} zoom={12} scrollWheelZoom={false} className={styles.leaflet}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {contorno && (
          <GeoJSON
            data={contorno}
            style={{
              color: 'var(--fa-color-action-primary)',
              weight: 2,
              fillOpacity: 0.04,
              dashArray: '6 6',
            }}
          />
        )}
        {children}
      </MapContainer>
    </div>
  )
}

/** Marcador sem imagem externa (o icone padrao do Leaflet quebra com bundlers). */
export function iconeDeMarcador(classe: string, html: string): L.DivIcon {
  return L.divIcon({ className: classe, html, iconSize: [36, 36], iconAnchor: [18, 18] })
}

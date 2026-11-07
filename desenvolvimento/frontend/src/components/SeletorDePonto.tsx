import { Marker, useMapEvents } from 'react-leaflet'
import { iconeDeMarcador } from './MapaBase'

export type Ponto = { lat: number; lon: number }

const ICONE = iconeDeMarcador(
  'fa-marcador-selecao',
  '<span style="display:block;width:20px;height:20px;border-radius:50%;background:var(--fa-color-action-primary);border:3px solid var(--fa-color-content-primary)"></span>',
)

/** Toque no mapa escolhe o ponto da ocorrência. */
export function SeletorDePonto({
  ponto,
  onChange,
}: {
  ponto: Ponto | null
  onChange: (p: Ponto) => void
}) {
  useMapEvents({ click: (e) => onChange({ lat: e.latlng.lat, lon: e.latlng.lng }) })
  return ponto ? <Marker position={[ponto.lat, ponto.lon]} icon={ICONE} /> : null
}

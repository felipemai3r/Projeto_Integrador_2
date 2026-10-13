import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AlertBanner } from './components/AlertBanner'
import { Header } from './components/Header'
import { Navegacao } from './components/Navegacao'
import { OfficialNotice } from './components/OfficialNotice'
import { Skeleton } from './components/Skeleton'
import { useAlertasVigentes } from './hooks/useDados'
import { ComoFunciona } from './pages/ComoFunciona'
import { Painel } from './pages/Painel'
import styles from './App.module.css'

// Mapa e formularios carregam sob demanda: o Leaflet nao pesa na tela inicial
const Mapa = lazy(() => import('./pages/Mapa').then((m) => ({ default: m.Mapa })))
const Moderacao = lazy(() => import('./pages/Moderacao').then((m) => ({ default: m.Moderacao })))
const Registrar = lazy(() => import('./pages/Registrar').then((m) => ({ default: m.Registrar })))

export function App() {
  const alertas = useAlertasVigentes()
  return (
    <>
      <Header />
      <Navegacao />
      <main className={`fa-container ${styles.principal}`}>
        {alertas.data && <AlertBanner alertas={alertas.data} />}
        <Suspense fallback={<Skeleton altura={240} />}>
          <Routes>
            <Route path="/" element={<Painel />} />
            <Route path="/mapa" element={<Mapa />} />
            <Route path="/registrar" element={<Registrar />} />
            <Route path="/moderacao" element={<Moderacao />} />
            <Route path="/como-funciona" element={<ComoFunciona />} />
            <Route path="*" element={<Painel />} />
          </Routes>
        </Suspense>
        <OfficialNotice />
      </main>
    </>
  )
}

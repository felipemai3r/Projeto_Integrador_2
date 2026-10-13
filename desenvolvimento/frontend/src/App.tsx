import { Route, Routes } from 'react-router-dom'
import { AlertBanner } from './components/AlertBanner'
import { Header } from './components/Header'
import { Navegacao } from './components/Navegacao'
import { OfficialNotice } from './components/OfficialNotice'
import { useAlertasVigentes } from './hooks/useDados'
import { ComoFunciona } from './pages/ComoFunciona'
import { Painel } from './pages/Painel'
import styles from './App.module.css'

export function App() {
  const alertas = useAlertasVigentes()
  return (
    <>
      <Header />
      <Navegacao />
      <main className={`fa-container ${styles.principal}`}>
        {alertas.data && <AlertBanner alertas={alertas.data} />}
        <Routes>
          <Route path="/" element={<Painel />} />
          <Route path="/como-funciona" element={<ComoFunciona />} />
          <Route path="*" element={<Painel />} />
        </Routes>
        <OfficialNotice />
      </main>
    </>
  )
}

import { AlertBanner } from './components/AlertBanner'
import { Header } from './components/Header'
import { OfficialNotice } from './components/OfficialNotice'
import { useAlertasVigentes } from './hooks/useDados'
import { Painel } from './pages/Painel'
import styles from './App.module.css'

export function App() {
  const alertas = useAlertasVigentes()
  return (
    <>
      <Header />
      <main className={`fa-container ${styles.principal}`}>
        {alertas.data && <AlertBanner alertas={alertas.data} />}
        <Painel />
        <OfficialNotice />
      </main>
    </>
  )
}

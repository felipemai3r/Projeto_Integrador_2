import { Header } from './components/Header'
import { OfficialNotice } from './components/OfficialNotice'
import { Painel } from './pages/Painel'
import styles from './App.module.css'

export function App() {
  return (
    <>
      <Header />
      <main className={`fa-container ${styles.principal}`}>
        <Painel />
        <OfficialNotice />
      </main>
    </>
  )
}

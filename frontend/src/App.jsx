import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { getCurrentUser, signOut } from 'aws-amplify/auth'
import Login from './Login.jsx'
import { DadosProvider } from './dados.jsx'
import Socios from './pages/Socios.jsx'
import SocioFicha from './pages/SocioFicha.jsx'
import SocioForm from './pages/SocioForm.jsx'
import Estatisticas from './pages/Estatisticas.jsx'
import Planos from './pages/Planos.jsx'
import Inicio from './pages/Inicio.jsx'
import Assistente from './pages/Assistente.jsx'
import logo from './assets/logo.png'

export default function App() {
  // undefined = ainda a verificar sessao; null = sem sessao
  const [user, setUser] = useState(undefined)

  const verificar = () =>
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))

  useEffect(() => {
    verificar()
  }, [])

  if (user === undefined) return <div className="a-carregar">A carregar…</div>
  if (user === null) return <Login onEntrar={verificar} />

  const sair = async () => {
    await signOut()
    setUser(null)
  }

  return (
    <BrowserRouter>
      <DadosProvider>
        <header className="nav">
          <div className="wrap">
            <NavLink to="/" className="nav-logo" aria-label="Início">
              <img src={logo} alt="Ativo Fitness" />
            </NavLink>
            <nav>
              <NavLink to="/" end>Início</NavLink>
              <NavLink to="/socios">Sócios</NavLink>
              <NavLink to="/estatisticas">Estatísticas</NavLink>
              <NavLink to="/planos">Planos</NavLink>
              <NavLink to="/assistente">Assistente</NavLink>
              <button className="nav-sair" onClick={sair}>Sair</button>
            </nav>
          </div>
        </header>
        <main className="wrap conteudo">
          <Routes>
            <Route path="/" element={<Inicio />} />
            <Route path="/socios" element={<Socios />} />
            <Route path="/socios/novo" element={<SocioForm />} />
            <Route path="/socios/:id" element={<SocioFicha />} />
            <Route path="/socios/:id/editar" element={<SocioForm />} />
            <Route path="/estatisticas" element={<Estatisticas />} />
            <Route path="/planos" element={<Planos />} />
            <Route path="/assistente" element={<Assistente />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </DadosProvider>
    </BrowserRouter>
  )
}

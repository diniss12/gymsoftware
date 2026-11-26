// Estado partilhado: a lista de socios e de planos e carregada UMA vez depois
// do login (~300 socios = 1 pedido) e reaproveitada por todas as paginas.
// Pesquisa e estatisticas trabalham sobre esta lista, sem novos pedidos.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api.js'

const Ctx = createContext(null)

export function DadosProvider({ children }) {
  const [socios, setSocios] = useState(null)
  const [planos, setPlanos] = useState(null)
  const [erro, setErro] = useState(null)

  const recarregar = useCallback(async () => {
    setErro(null)
    try {
      const [s, p] = await Promise.all([api('/socios'), api('/planos')])
      setSocios(s)
      setPlanos(p)
    } catch (e) {
      setErro(e.message)
    }
  }, [])

  useEffect(() => {
    recarregar()
  }, [recarregar])

  /** Atualiza (ou acrescenta) um socio na lista local depois de uma gravacao. */
  const guardarSocio = useCallback((socio) => {
    const { historico, ...ficha } = socio
    setSocios((lista) => {
      const outros = (lista ?? []).filter((s) => s.id !== ficha.id)
      return [...outros, ficha].sort((a, b) => a.nome.localeCompare(b.nome, 'pt'))
    })
  }, [])

  const guardarPlano = useCallback((plano) => {
    setPlanos((lista) => {
      const outros = (lista ?? []).filter((p) => p.id !== plano.id)
      return [...outros, plano].sort((a, b) => a.nome.localeCompare(b.nome, 'pt'))
    })
  }, [])

  const planoPorId = useMemo(() => Object.fromEntries((planos ?? []).map((p) => [p.id, p])), [planos])

  const valor = { socios, planos, planoPorId, erro, recarregar, guardarSocio, guardarPlano }
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>
}

export const useDados = () => useContext(Ctx)

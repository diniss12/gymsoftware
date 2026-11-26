import { useMemo, useState } from 'react'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { euros, paraCentimos, vezes } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

export default function Planos() {
  return (
    <Aguardar>
      <Lista />
    </Aguardar>
  )
}

function Lista() {
  const { planos, socios } = useDados()
  const [aEditar, setAEditar] = useState(null) // id do plano, ou 'novo'

  const sociosPorPlano = useMemo(() => {
    const m = {}
    for (const s of socios) if (s.estado === 'ATIVO') m[s.planoId] = (m[s.planoId] ?? 0) + 1
    return m
  }, [socios])

  return (
    <>
      <Cabecalho eyebrow="Mensais · sem fidelização" titulo="Planos">
        {aEditar !== 'novo' && (
          <button className="btn btn-red" onClick={() => setAEditar('novo')}>+ Novo plano</button>
        )}
      </Cabecalho>

      <p className="muted aviso-plano">
        Mudar o preço de um plano não altera o histórico: cada sócio guarda o preço que estava em vigor quando entrou nesse plano.
      </p>

      {aEditar === 'novo' && <FormPlano onFechar={() => setAEditar(null)} />}

      <div className="planos-grelha">
        {planos.map((p) =>
          aEditar === p.id ? (
            <FormPlano key={p.id} plano={p} onFechar={() => setAEditar(null)} />
          ) : (
            <article key={p.id} className={`plano-cartao${p.ativo ? '' : ' plano-inativo'}`}>
              <p className="cartao-lbl">{p.nome}{!p.ativo && ' · desativado'}</p>
              <p className="plano-preco">
                {euros(p.precoMensal).replace(/\s?€/, '')}<sup>€</sup><small>/mês</small>
              </p>
              <p className="muted">{vezes(p)} · {sociosPorPlano[p.id] ?? 0} sócio(s) ativo(s)</p>
              <button className="btn btn-ghost btn-pequeno" onClick={() => setAEditar(p.id)}>Editar</button>
            </article>
          ),
        )}
      </div>
    </>
  )
}

function FormPlano({ plano, onFechar }) {
  const { guardarPlano } = useDados()
  const [nome, setNome] = useState(plano?.nome ?? '')
  const [vez, setVez] = useState(plano?.vezesPorSemana ?? '')
  const [preco, setPreco] = useState(plano ? (plano.precoMensal / 100).toFixed(2).replace('.', ',') : '')
  const [ativo, setAtivo] = useState(plano?.ativo ?? true)
  const [erro, setErro] = useState('')
  const [aGravar, setAGravar] = useState(false)

  async function gravar(ev) {
    ev.preventDefault()
    const precoMensal = paraCentimos(preco)
    if (precoMensal === null) return setErro('Preço inválido.')
    setErro('')
    setAGravar(true)
    const body = { nome, precoMensal, vezesPorSemana: vez === '' ? null : Number(vez), ativo }
    try {
      const gravado = plano
        ? await api(`/planos/${plano.id}`, { method: 'PUT', body })
        : await api('/planos', { method: 'POST', body })
      guardarPlano(gravado)
      onFechar()
    } catch (e) {
      setErro(e.message)
      setAGravar(false)
    }
  }

  return (
    <form className="painel-acao plano-form" onSubmit={gravar}>
      <p className="eyebrow">{plano ? 'Editar plano' : 'Novo plano'}</p>
      <div className="painel-campos">
        <label>
          Nome
          <input value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={60} autoFocus />
        </label>
        <label>
          Vezes por semana
          <select value={vez} onChange={(e) => setVez(e.target.value)}>
            <option value="">Livre (sem limite)</option>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>{n}× semana</option>
            ))}
          </select>
        </label>
        <label>
          Preço mensal (€)
          <input value={preco} onChange={(e) => setPreco(e.target.value)} inputMode="decimal" placeholder="25,00" required />
        </label>
        <label className="check">
          <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
          Disponível para novas inscrições
        </label>
      </div>
      <Erro>{erro}</Erro>
      <div className="formulario-acoes">
        <button className="btn btn-red" disabled={aGravar}>{aGravar ? 'A gravar…' : 'Guardar'}</button>
        <button type="button" className="btn btn-ghost" onClick={onFechar}>Cancelar</button>
      </div>
    </form>
  )
}

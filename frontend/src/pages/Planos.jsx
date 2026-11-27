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
      <Cabecalho titulo="Planos" descricao="Planos mensais, sem fidelização.">
        {!aEditar && (
          <button className="btn btn-primario" onClick={() => setAEditar('novo')}>Novo plano</button>
        )}
      </Cabecalho>

      {aEditar && (
        <FormPlano
          key={aEditar}
          plano={planos.find((p) => p.id === aEditar)}
          onFechar={() => setAEditar(null)}
        />
      )}

      <div className="tabela-scroll">
        <table className="tabela">
          <thead>
            <tr>
              <th>Plano</th>
              <th>Frequência</th>
              <th className="num">Preço mensal</th>
              <th className="num">Sócios ativos</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {planos.map((p) => (
              <tr key={p.id} className={p.ativo ? undefined : 'linha-inativa'}>
                <td>{p.nome}</td>
                <td>{vezes(p)}</td>
                <td className="num">{euros(p.precoMensal)}</td>
                <td className="num">{sociosPorPlano[p.id] ?? 0}</td>
                <td><span className="etiqueta">{p.ativo ? 'Disponível' : 'Desativado'}</span></td>
                <td className="num">
                  <button className="btn btn-pequeno" onClick={() => setAEditar(p.id)} disabled={!!aEditar}>Editar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="texto-ajuda rodape">
        Mudar o preço de um plano não altera o histórico: cada sócio guarda o preço que estava em vigor quando entrou nesse plano.
      </p>
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
    <form className="painel-acao" onSubmit={gravar}>
      <h2 className="painel-titulo">{plano ? 'Editar plano' : 'Novo plano'}</h2>
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
        <button className="btn btn-primario" disabled={aGravar}>{aGravar ? 'A gravar…' : 'Guardar'}</button>
        <button type="button" className="btn" onClick={onFechar}>Cancelar</button>
      </div>
    </form>
  )
}

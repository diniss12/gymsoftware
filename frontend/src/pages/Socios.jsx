import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDados } from '../dados.jsx'
import { dataPt, idade, normalizar } from '../util.js'
import { Aguardar, Cabecalho } from './comum.jsx'

export default function Socios() {
  return (
    <Aguardar>
      <Lista />
    </Aguardar>
  )
}

function Lista() {
  const { socios, planos, planoPorId } = useDados()
  const navigate = useNavigate()
  const [pesquisa, setPesquisa] = useState('')
  const [estado, setEstado] = useState('ATIVO')
  const [plano, setPlano] = useState('')

  // Pesquisa feita no browser: com ~300 socios e instantanea e nao gasta pedidos.
  const visiveis = useMemo(() => {
    const termo = normalizar(pesquisa.trim())
    return socios.filter(
      (s) =>
        (!estado || s.estado === estado) &&
        (!plano || s.planoId === plano) &&
        (!termo || normalizar(s.nome).includes(termo) || s.nif.includes(termo)),
    )
  }, [socios, pesquisa, estado, plano])

  return (
    <>
      <Cabecalho eyebrow={`${visiveis.length} de ${socios.length}`} titulo="Sócios">
        <Link to="/socios/novo" className="btn btn-red">+ Novo sócio</Link>
      </Cabecalho>

      <div className="filtros">
        <input
          type="search"
          placeholder="Procurar por nome ou NIF…"
          value={pesquisa}
          onChange={(e) => setPesquisa(e.target.value)}
          autoFocus
        />
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="ATIVO">Ativos</option>
          <option value="INATIVO">Inativos</option>
          <option value="">Todos</option>
        </select>
        <select value={plano} onChange={(e) => setPlano(e.target.value)} aria-label="Plano">
          <option value="">Todos os planos</option>
          {planos.map((p) => (
            <option key={p.id} value={p.id}>{p.nome}</option>
          ))}
        </select>
      </div>

      {visiveis.length === 0 ? (
        <p className="vazio">
          {socios.length === 0 ? 'Ainda não há sócios. Começa por inscrever o primeiro.' : 'Nenhum sócio corresponde à pesquisa.'}
        </p>
      ) : (
        <div className="tabela-scroll">
          <table className="tabela tabela-clicavel">
            <thead>
              <tr>
                <th>Nome</th>
                <th>NIF</th>
                <th>Plano</th>
                <th>Localidade</th>
                <th className="num">Idade</th>
                <th>Sócio desde</th>
              </tr>
            </thead>
            <tbody>
              {visiveis.map((s) => (
                <tr key={s.id} onClick={() => navigate(`/socios/${s.id}`)}>
                  <td>
                    <Link to={`/socios/${s.id}`} onClick={(e) => e.stopPropagation()}>{s.nome}</Link>
                    {s.estado === 'INATIVO' && <span className="etiqueta">Inativo</span>}
                  </td>
                  <td className="mono">{s.nif}</td>
                  <td>{planoPorId[s.planoId]?.nome ?? '—'}</td>
                  <td>{s.localidade || '—'}</td>
                  <td className="num">{idade(s.dataNascimento)}</td>
                  <td>{dataPt(s.dataEntrada)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { SEXOS, dataPt, euros, hojeISO, idade, vezes } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

export default function SocioFicha() {
  return (
    <Aguardar>
      <Ficha />
    </Aguardar>
  )
}

function Ficha() {
  const { id } = useParams()
  const { planoPorId, guardarSocio } = useDados()
  const [socio, setSocio] = useState(null)
  const [erro, setErro] = useState('')
  const [acao, setAcao] = useState(null) // 'plano' | 'inativar' | 'reativar'

  useEffect(() => {
    setSocio(null)
    api(`/socios/${id}`).then(setSocio).catch((e) => setErro(e.message))
  }, [id])

  if (!socio) return erro ? <Erro>{erro}</Erro> : <p className="muted">A carregar…</p>

  const atualizado = (s) => {
    setSocio(s)
    guardarSocio(s)
    setAcao(null)
  }
  const ativo = socio.estado === 'ATIVO'
  const plano = planoPorId[socio.planoId]
  const historico = [...socio.historico].reverse() // mais recente primeiro

  return (
    <>
      <Cabecalho eyebrow={ativo ? 'Sócio ativo' : `Inativo desde ${dataPt(socio.dataSaida)}`} titulo={socio.nome}>
        <Link to={`/socios/${id}/editar`} className="btn btn-ghost">Editar dados</Link>
        {ativo ? (
          <>
            <button className="btn btn-ghost" onClick={() => setAcao('plano')}>Mudar plano</button>
            <button className="btn btn-ghost" onClick={() => setAcao('inativar')}>Inativar</button>
          </>
        ) : (
          <button className="btn btn-red" onClick={() => setAcao('reativar')}>Reativar</button>
        )}
      </Cabecalho>

      {acao && <Acao acao={acao} socio={socio} onFeito={atualizado} onCancelar={() => setAcao(null)} />}

      <div className="ficha-grelha">
        <section className="cartao cartao-destaque">
          <p className="cartao-lbl">Plano atual</p>
          {ativo && plano ? (
            <>
              <p className="cartao-grande">{plano.nome}</p>
              <p className="muted">{euros(plano.precoMensal)}/mês · {vezes(plano)} · desde {dataPt(socio.planoDesde)}</p>
            </>
          ) : (
            <p className="cartao-grande">Sem plano</p>
          )}
        </section>

        <section className="cartao">
          <dl className="dados">
            <dt>NIF</dt><dd className="mono">{socio.nif}</dd>
            <dt>Sexo</dt><dd>{SEXOS[socio.sexo] ?? '—'}</dd>
            <dt>Nascimento</dt><dd>{dataPt(socio.dataNascimento)} ({idade(socio.dataNascimento)} anos)</dd>
            <dt>Sócio desde</dt><dd>{dataPt(socio.dataEntrada)}</dd>
            <dt>Morada</dt><dd>{socio.morada || '—'}</dd>
            <dt>Localidade</dt><dd>{socio.localidade || '—'}</dd>
          </dl>
        </section>

        {socio.notas && (
          <section className="cartao col-total">
            <p className="cartao-lbl">Notas</p>
            <p className="notas">{socio.notas}</p>
          </section>
        )}
      </div>

      <h2 className="subtitulo">Histórico de planos</h2>
      <div className="tabela-scroll">
        <table className="tabela">
          <thead>
            <tr>
              <th>Plano</th>
              <th className="num">Preço na altura</th>
              <th>Início</th>
              <th>Fim</th>
            </tr>
          </thead>
          <tbody>
            {historico.map((p) => (
              <tr key={p.id}>
                <td>{p.planoNome}</td>
                <td className="num">{euros(p.precoMensal)}</td>
                <td>{dataPt(p.dataInicio)}</td>
                <td>{p.dataFim ? dataPt(p.dataFim) : <span className="etiqueta etiqueta-red">Atual</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

const TEXTOS = {
  plano: { titulo: 'Mudar de plano', botao: 'Mudar plano', data: 'A partir de' },
  inativar: { titulo: 'Inativar sócio', botao: 'Inativar', data: 'Data de saída' },
  reativar: { titulo: 'Reativar sócio', botao: 'Reativar', data: 'A partir de' },
}

function Acao({ acao, socio, onFeito, onCancelar }) {
  const { planos } = useDados()
  const [planoId, setPlanoId] = useState('')
  const [data, setData] = useState(hojeISO())
  const [erro, setErro] = useState('')
  const [aGravar, setAGravar] = useState(false)
  const t = TEXTOS[acao]
  const opcoes = planos.filter((p) => p.ativo && !(acao === 'plano' && p.id === socio.planoId))

  async function confirmar(ev) {
    ev.preventDefault()
    setErro('')
    setAGravar(true)
    try {
      const body = acao === 'inativar' ? { data } : { planoId, data }
      onFeito(await api(`/socios/${socio.id}/${acao}`, { method: 'POST', body }))
    } catch (e) {
      setErro(e.message)
      setAGravar(false)
    }
  }

  return (
    <form className="painel-acao" onSubmit={confirmar}>
      <p className="eyebrow">{t.titulo}</p>
      <div className="painel-campos">
        {acao !== 'inativar' && (
          <label>
            Novo plano
            <select value={planoId} onChange={(e) => setPlanoId(e.target.value)} required autoFocus>
              <option value="" disabled>Escolhe…</option>
              {opcoes.map((p) => (
                <option key={p.id} value={p.id}>{p.nome} — {euros(p.precoMensal)}/mês</option>
              ))}
            </select>
          </label>
        )}
        <label>
          {t.data}
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} max={hojeISO()} required />
        </label>
      </div>
      {acao === 'inativar' && (
        <p className="muted">O plano atual é fechado nesta data. Nada é apagado: a ficha e o histórico ficam guardados.</p>
      )}
      <Erro>{erro}</Erro>
      <div className="formulario-acoes">
        <button className="btn btn-red" disabled={aGravar}>{aGravar ? 'A gravar…' : t.botao}</button>
        <button type="button" className="btn btn-ghost" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}

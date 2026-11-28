// Pagamentos na ficha do socio: formulario de registo + historico.
// O que falta pagar (socio.situacao) vem calculado do backend (regras.py).

import { useState } from 'react'
import { api } from '../api.js'
import { METODOS, dataPt, euros, hojeISO, mesCurto, mesNome, mesSeguinte, paraCentimos } from '../util.js'
import { Erro } from './comum.jsx'

export function RegistarPagamento({ socio, onFeito, onCancelar }) {
  const { emAtraso, dentroDoPrazo } = socio.situacao
  const pagos = new Set(socio.pagamentos.map((p) => p.mes))
  const proximo = mesSeguinte(hojeISO().slice(0, 7))

  // Opcoes: meses em divida (mais antigo primeiro) + mes seguinte (pagar adiantado).
  const opcoes = [...emAtraso, ...dentroDoPrazo]
  if (!pagos.has(proximo) && socio.estado === 'ATIVO') {
    const atual = socio.historico.find((p) => !p.dataFim)
    opcoes.push({ mes: proximo, valor: atual?.precoMensal ?? 0, adiantado: true })
  }

  const [mes, setMes] = useState(opcoes[0]?.mes ?? 'outro')
  const [outroMes, setOutroMes] = useState('')
  const [valor, setValor] = useState(opcoes[0] ? (opcoes[0].valor / 100).toFixed(2).replace('.', ',') : '')
  const [metodo, setMetodo] = useState('MBWAY')
  const [data, setData] = useState(hojeISO())
  const [notas, setNotas] = useState('')
  const [erro, setErro] = useState('')
  const [aGravar, setAGravar] = useState(false)

  const escolherMes = (m) => {
    setMes(m)
    const o = opcoes.find((x) => x.mes === m)
    if (o) setValor((o.valor / 100).toFixed(2).replace('.', ','))
  }

  async function gravar(ev) {
    ev.preventDefault()
    const mesFinal = mes === 'outro' ? outroMes : mes
    const centimos = paraCentimos(valor)
    if (!mesFinal) return setErro('Escolhe o mês.')
    if (centimos === null) return setErro('Valor inválido.')
    setErro('')
    setAGravar(true)
    try {
      const p = await api(`/socios/${socio.id}/pagamentos`, {
        method: 'POST',
        body: { mes: mesFinal, valor: centimos, metodo, dataPagamento: data, notas },
      })
      onFeito(p)
    } catch (e) {
      setErro(e.message)
      setAGravar(false)
    }
  }

  return (
    <form className="painel-acao" onSubmit={gravar}>
      <h2 className="painel-titulo">Registar pagamento</h2>
      <div className="painel-campos">
        <label>
          Mês da mensalidade
          <select value={mes} onChange={(e) => escolherMes(e.target.value)} required autoFocus>
            {opcoes.map((o) => (
              <option key={o.mes} value={o.mes}>
                {mesNome(o.mes)}
                {emAtraso.some((x) => x.mes === o.mes) ? ' — em atraso' : o.adiantado ? ' — adiantado' : ''}
              </option>
            ))}
            <option value="outro">Outro mês…</option>
          </select>
        </label>
        {mes === 'outro' && (
          <label>
            Qual mês
            <input type="month" value={outroMes} onChange={(e) => setOutroMes(e.target.value)} required />
          </label>
        )}
        <label>
          Valor (€)
          <input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="decimal" required />
        </label>
        <label>
          Data do pagamento
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} max={hojeISO()} required />
        </label>
      </div>
      <fieldset className="metodos">
        <legend>Método</legend>
        <div className="metodos-opcoes">
          {Object.entries(METODOS).map(([k, nome]) => (
            <label key={k} className={`metodo${metodo === k ? ' metodo-ativo' : ''}`}>
              <input type="radio" name="metodo" value={k} checked={metodo === k} onChange={() => setMetodo(k)} />
              {nome}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="painel-notas">
        Notas
        <textarea value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={500} placeholder="Opcional" />
      </label>
      <Erro>{erro}</Erro>
      <div className="formulario-acoes">
        <button className="btn btn-primario" disabled={aGravar}>{aGravar ? 'A gravar…' : 'Registar pagamento'}</button>
        <button type="button" className="btn" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}

export function HistoricoPagamentos({ socio, onApagado }) {
  const { emAtraso, dentroDoPrazo } = socio.situacao
  const [erro, setErro] = useState('')
  const lista = [...socio.pagamentos].reverse() // mais recente primeiro

  async function apagar(p) {
    if (!window.confirm(`Apagar o pagamento de ${mesNome(p.mes)} (${euros(p.valor)})?`)) return
    setErro('')
    try {
      await api(`/socios/${socio.id}/pagamentos/${p.mes}`, { method: 'DELETE' })
      onApagado()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <>
      <h2 className="subtitulo">Pagamentos</h2>
      {(emAtraso.length > 0 || dentroDoPrazo.length > 0) && (
        <div className="por-pagar">
          {emAtraso.map((d) => (
            <span key={d.mes} className="chip chip-atraso" title={`Prazo: ${dataPt(d.prazo)}`}>
              {mesCurto(d.mes)} · {euros(d.valor)} · em atraso
            </span>
          ))}
          {dentroDoPrazo.map((d) => (
            <span key={d.mes} className="chip" title={`Prazo: ${dataPt(d.prazo)}`}>
              {mesCurto(d.mes)} · {euros(d.valor)} · até {dataPt(d.prazo).slice(0, 5)}
            </span>
          ))}
        </div>
      )}
      <Erro>{erro}</Erro>
      {lista.length === 0 ? (
        <p className="vazio">Ainda não há pagamentos registados.</p>
      ) : (
        <div className="tabela-scroll">
          <table className="tabela">
            <thead>
              <tr>
                <th>Mês</th>
                <th className="num">Valor</th>
                <th>Método</th>
                <th>Pago em</th>
                <th>Notas</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {lista.map((p) => (
                <tr key={p.mes}>
                  <td>{mesNome(p.mes)}</td>
                  <td className="num">{euros(p.valor)}</td>
                  <td>{METODOS[p.metodo] ?? p.metodo}</td>
                  <td>{dataPt(p.dataPagamento)}</td>
                  <td className="celula-notas">{p.notas || '—'}</td>
                  <td className="num">
                    <button className="btn-texto" onClick={() => apagar(p)}>Apagar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

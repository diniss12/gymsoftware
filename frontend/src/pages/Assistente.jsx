// Chat com o assistente (POST /chat). O historico vive so nesta pagina e e
// enviado inteiro em cada pergunta (o backend nao guarda conversas).
// Pagamentos propostos pelo assistente aparecem como cartoes: so ao carregar
// em "Confirmar" e que se chama a API normal e o pagamento fica registado.

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { METODOS, dataPt, euros, mesNome } from '../util.js'
import { Cabecalho } from './comum.jsx'

const SUGESTOES = [
  'Quem tem mensalidades em atraso?',
  'Quanto recebi este mês?',
  'Quantos sócios ativos há por plano?',
]

export default function Assistente() {
  // mensagens: { role: 'user' | 'assistant', texto, propostas? }
  const [mensagens, setMensagens] = useState([])
  const [texto, setTexto] = useState('')
  const [aPensar, setAPensar] = useState(false)
  const [erro, setErro] = useState('')
  const fim = useRef(null)

  useEffect(() => {
    fim.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensagens, aPensar])

  async function enviar(pergunta) {
    const t = pergunta.trim()
    if (!t || aPensar) return
    const novas = [...mensagens, { role: 'user', texto: t }]
    setMensagens(novas)
    setTexto('')
    setErro('')
    setAPensar(true)
    try {
      const r = await api('/chat', {
        method: 'POST',
        body: { mensagens: novas.map(({ role, texto }) => ({ role, texto })) },
      })
      setMensagens([...novas, { role: 'assistant', texto: r.resposta, propostas: r.propostas }])
    } catch (e) {
      setErro(e.message)
      setMensagens(mensagens) // devolve a pergunta ao campo para tentar de novo
      setTexto(t)
    } finally {
      setAPensar(false)
    }
  }

  return (
    <>
      <Cabecalho titulo="Assistente" descricao="Pergunta sobre sócios, pagamentos e receita, ou regista pagamentos.">
        {mensagens.length > 0 && (
          <button className="btn" onClick={() => setMensagens([])} disabled={aPensar}>Nova conversa</button>
        )}
      </Cabecalho>

      <div className="chat">
        {mensagens.length === 0 && (
          <div className="chat-vazio">
            <p className="muted">Exemplos:</p>
            <div className="chat-sugestoes">
              {[...SUGESTOES, 'O Leandro pagou novembro em dinheiro'].map((s) => (
                <button key={s} className="btn btn-pequeno" onClick={() => enviar(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {mensagens.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            <div className="chat-bolha">{m.texto}</div>
            {m.propostas?.map((p, j) => <PropostaPagamento key={j} proposta={p} />)}
          </div>
        ))}
        {aPensar && <div className="chat-msg chat-assistant"><div className="chat-bolha muted">A pensar…</div></div>}
        <div ref={fim} />
      </div>

      {erro && <p className="aviso aviso-erro" role="alert">{erro}</p>}

      <form className="chat-form" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escreve uma pergunta…"
          maxLength={2000}
          disabled={aPensar}
          autoFocus
        />
        <button className="btn btn-primario" disabled={aPensar || !texto.trim()}>Enviar</button>
      </form>
      <p className="texto-ajuda rodape">
        O assistente pode enganar-se. Confirma sempre os dados antes de registar um pagamento.
      </p>
    </>
  )
}

/** Cartao de confirmacao: so aqui o pagamento e gravado (POST normal da API). */
function PropostaPagamento({ proposta: p }) {
  const [estado, setEstado] = useState('pendente') // pendente | a-gravar | registado | cancelado
  const [erro, setErro] = useState('')

  async function confirmar() {
    setEstado('a-gravar')
    setErro('')
    try {
      await api(`/socios/${p.socioId}/pagamentos`, {
        method: 'POST',
        body: { mes: p.mes, valor: p.valor, metodo: p.metodo, dataPagamento: p.dataPagamento, notas: p.notas },
      })
      setEstado('registado')
    } catch (e) {
      setErro(e.message)
      setEstado('pendente')
    }
  }

  return (
    <div className={`proposta proposta-${estado}`}>
      <p className="proposta-titulo">Registar pagamento</p>
      <dl className="dados">
        <dt>Sócio</dt><dd><Link to={`/socios/${p.socioId}`}>{p.nome}</Link></dd>
        <dt>Mensalidade</dt><dd>{mesNome(p.mes)}</dd>
        <dt>Valor</dt><dd>{euros(p.valor)}</dd>
        <dt>Método</dt><dd>{METODOS[p.metodo] ?? p.metodo}</dd>
        <dt>Pago em</dt><dd>{dataPt(p.dataPagamento)}</dd>
        {p.notas && (<><dt>Notas</dt><dd>{p.notas}</dd></>)}
      </dl>
      {erro && <p className="campo-erro">{erro}</p>}
      {estado === 'registado' && <p className="proposta-estado">Pagamento registado.</p>}
      {estado === 'cancelado' && <p className="proposta-estado muted">Cancelado. Nada foi registado.</p>}
      {(estado === 'pendente' || estado === 'a-gravar') && (
        <div className="formulario-acoes">
          <button className="btn btn-primario btn-pequeno" onClick={confirmar} disabled={estado === 'a-gravar'}>
            {estado === 'a-gravar' ? 'A registar…' : 'Confirmar'}
          </button>
          <button className="btn btn-pequeno" onClick={() => setEstado('cancelado')} disabled={estado === 'a-gravar'}>
            Cancelar
          </button>
        </div>
      )}
    </div>
  )
}

import { useDados } from '../dados.jsx'

/** Mostra "a carregar" / erro enquanto a lista de socios e planos nao chega. */
export function Aguardar({ children }) {
  const { socios, planos, erro, recarregar } = useDados()
  if (erro)
    return (
      <div className="aviso aviso-erro">
        <p>Não foi possível carregar os dados: {erro}</p>
        <button className="btn" onClick={recarregar}>Tentar de novo</button>
      </div>
    )
  if (!socios || !planos) return <p className="muted">A carregar…</p>
  return children
}

export function Cabecalho({ titulo, descricao, children }) {
  return (
    <div className="cabecalho">
      <div>
        <h1 className="titulo">{titulo}</h1>
        {descricao && <p className="descricao">{descricao}</p>}
      </div>
      {children && <div className="cabecalho-acoes">{children}</div>}
    </div>
  )
}

export function Erro({ children }) {
  return children ? <p className="aviso aviso-erro" role="alert">{children}</p> : null
}

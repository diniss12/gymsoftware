import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { SEXOS, euros, hojeISO, nifValido, vezes } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

const VAZIO = {
  nome: '',
  nif: '',
  sexo: '',
  dataNascimento: '',
  dataEntrada: hojeISO(),
  morada: '',
  localidade: '',
  notas: '',
  planoId: '',
}

export default function SocioForm() {
  return (
    <Aguardar>
      <Formulario />
    </Aguardar>
  )
}

function Formulario() {
  const { id } = useParams() // undefined = novo socio
  const navigate = useNavigate()
  const { planos, guardarSocio } = useDados()
  const [form, setForm] = useState(id ? null : { ...VAZIO, dataEntrada: hojeISO() })
  const [erro, setErro] = useState('')
  const [aGravar, setAGravar] = useState(false)

  useEffect(() => {
    if (!id) return
    api(`/socios/${id}`)
      .then((s) => setForm({ ...VAZIO, ...s }))
      .catch((e) => setErro(e.message))
  }, [id])

  if (!form) return erro ? <Erro>{erro}</Erro> : <p className="muted">A carregar…</p>

  const muda = (campo) => (e) => setForm({ ...form, [campo]: e.target.value })
  const nifMal = form.nif.length === 9 && !nifValido(form.nif)
  const planosAtivos = planos.filter((p) => p.ativo)

  async function gravar(ev) {
    ev.preventDefault()
    if (!nifValido(form.nif)) return setErro('NIF inválido.')
    setErro('')
    setAGravar(true)
    const { nome, nif, sexo, dataNascimento, dataEntrada, morada, localidade, notas, planoId } = form
    const body = { nome, nif, sexo, dataNascimento, dataEntrada, morada, localidade, notas }
    try {
      const socio = id
        ? await api(`/socios/${id}`, { method: 'PUT', body })
        : await api('/socios', { method: 'POST', body: { ...body, planoId } })
      guardarSocio(socio)
      navigate(`/socios/${socio.id}`)
    } catch (e) {
      setErro(e.message)
      setAGravar(false)
    }
  }

  return (
    <>
      <Cabecalho titulo={id ? 'Editar sócio' : 'Novo sócio'} descricao={id ? form.nome : null} />
      <form className="formulario" onSubmit={gravar}>
        <fieldset>
          <legend>Dados pessoais</legend>
          <label className="col-2">
            Nome completo
            <input value={form.nome} onChange={muda('nome')} required maxLength={120} autoFocus />
          </label>
          <label>
            NIF
            <input
              value={form.nif}
              onChange={(e) => setForm({ ...form, nif: e.target.value.replace(/\D/g, '').slice(0, 9) })}
              inputMode="numeric"
              required
              aria-invalid={nifMal}
            />
            {nifMal && <span className="campo-erro">NIF inválido</span>}
          </label>
          <label>
            Sexo
            <select value={form.sexo} onChange={muda('sexo')} required>
              <option value="" disabled>Escolhe…</option>
              {Object.entries(SEXOS).map(([k, nome]) => (
                <option key={k} value={k}>{nome}</option>
              ))}
            </select>
          </label>
          <label>
            Data de nascimento
            <input type="date" value={form.dataNascimento} onChange={muda('dataNascimento')} max={hojeISO()} required />
          </label>
          <label className="col-2">
            Morada
            <input value={form.morada} onChange={muda('morada')} maxLength={200} />
          </label>
          <label>
            Localidade
            <input value={form.localidade} onChange={muda('localidade')} maxLength={80} />
          </label>
        </fieldset>

        <fieldset>
          <legend>Ginásio</legend>
          <label>
            Data de entrada
            <input type="date" value={form.dataEntrada} onChange={muda('dataEntrada')} max={hojeISO()} required />
            <span className="campo-dica">Hoje, ou uma data anterior.</span>
          </label>
          {!id && (
            <label className="col-2">
              Plano
              <select value={form.planoId} onChange={muda('planoId')} required>
                <option value="" disabled>Escolhe um plano…</option>
                {planosAtivos.map((p) => (
                  <option key={p.id} value={p.id}>{p.nome} — {euros(p.precoMensal)}/mês ({vezes(p)})</option>
                ))}
              </select>
            </label>
          )}
          <label className="col-3">
            Notas
            <textarea value={form.notas} onChange={muda('notas')} rows={4} maxLength={2000} />
          </label>
        </fieldset>

        <Erro>{erro}</Erro>
        <div className="formulario-acoes">
          <button className="btn btn-primario" disabled={aGravar}>{aGravar ? 'A gravar…' : id ? 'Guardar alterações' : 'Inscrever sócio'}</button>
          <Link to={id ? `/socios/${id}` : '/socios'} className="btn">Cancelar</Link>
        </div>
      </form>
    </>
  )
}

import { fetchAuthSession } from 'aws-amplify/auth'

const BASE = import.meta.env.VITE_API_URL

/**
 * Chama a API com o access token do Cognito no header Authorization.
 * O fetchAuthSession() renova o token sozinho quando expira (refresh token).
 * Em erro lanca um Error com a mensagem que a API devolveu ({"message": ...}).
 */
export async function api(caminho, { method = 'GET', body } = {}) {
  const { tokens } = await fetchAuthSession()
  if (!tokens?.accessToken) throw new Error('Sessão expirada. Volta a entrar.')

  const res = await fetch(BASE + caminho, {
    method,
    headers: {
      Authorization: `Bearer ${tokens.accessToken.toString()}`,
      ...(body !== undefined && { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const dados = await res.json().catch(() => null)
  if (!res.ok) throw new Error(dados?.message || `Erro ${res.status}`)
  return dados
}

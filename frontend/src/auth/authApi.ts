/** Auth endpoints (api_contract_spec.md Section 5.1.1). */
import { apiGet, apiPatch, apiPost } from '../api/client'

export interface User {
  id: string
  email: string
  display_name: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

const anonymous = { authenticated: false } as const

export const authApi = {
  register: (email: string, password: string, displayName?: string) =>
    apiPost<TokenResponse>(
      '/auth/register',
      { email, password, display_name: displayName || undefined },
      anonymous,
    ),
  login: (email: string, password: string) => apiPost<TokenResponse>('/auth/login', { email, password }, anonymous),
  refresh: () => apiPost<TokenResponse>('/auth/refresh', undefined, anonymous),
  logout: () => apiPost<void>('/auth/logout', undefined, anonymous),
  forgotPassword: (email: string) => apiPost<{ message: string }>('/auth/password/forgot', { email }, anonymous),
  resetPassword: (token: string, newPassword: string) =>
    apiPost<void>('/auth/password/reset', { token, new_password: newPassword }, anonymous),
  me: () => apiGet<User>('/users/me'),
  /** The user's name; empty removes it. */
  updateName: (displayName: string) => apiPatch<User>('/users/me', { display_name: displayName || null }),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiPost<void>('/auth/password/change', { current_password: currentPassword, new_password: newPassword }),
  deleteAccount: (password: string, confirmation: string) =>
    apiPost<void>('/auth/account/delete', { password, confirmation }),
}

export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_HINT = `At least ${PASSWORD_MIN_LENGTH} characters. A short sentence you don't use elsewhere works well.`

/**
 * Session state (frontend_spec.md Section 5).
 * The access token is kept in memory only; a page reload restores the session
 * through the HttpOnly refresh cookie.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { refreshAccessToken, setAccessToken, setRefreshHandler } from '../api/client'
import { authApi, type TokenResponse, type User } from './authApi'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: Status
  user: User | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
  /** Forget the session here without calling the server (the account was deleted). */
  endSession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)

  const applySession = useCallback((session: TokenResponse) => {
    setAccessToken(session.access_token)
    setUser(session.user)
    setStatus('authenticated')
  }, [])

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  useEffect(() => {
    // Used by the API client for silent renewal, and below to restore a session on load.
    setRefreshHandler(async () => {
      try {
        const session = await authApi.refresh()
        applySession(session)
        return session.access_token
      } catch {
        clearSession()
        return null
      }
    })

    // Shared single-flight call, so React StrictMode's double effect does not refresh twice.
    void refreshAccessToken()
    return () => setRefreshHandler(null)
  }, [applySession, clearSession])

  const login = useCallback(
    async (email: string, password: string) => applySession(await authApi.login(email, password)),
    [applySession],
  )

  const register = useCallback(
    async (email: string, password: string, displayName?: string) =>
      applySession(await authApi.register(email, password, displayName)),
    [applySession],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      // Clear local state even if the server call fails (frontend_spec.md Section 5).
      clearSession()
    }
  }, [clearSession])

  const value = useMemo(
    () => ({ status, user, login, register, logout, endSession: clearSession }),
    [status, user, login, register, logout, clearSession],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components -- the hook belongs with its provider
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

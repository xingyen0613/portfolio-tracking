import { createContext, useCallback, useContext, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

const TOKEN_KEY = 'portfolio_token'
const USER_KEY = 'portfolio_user'

interface User {
  id: string
  email: string
  name: string
  picture: string
}

interface AuthContextType {
  token: string | null
  user: User | null
  login: (credential: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  })

  const login = useCallback(async (credential: string) => {
    // Cloud Run scales to zero; a cold start can push this request past the
    // 10s client default (the server still returns 200, just late). Override
    // the timeout so a cold-start login succeeds instead of showing a false
    // "timeout of 10000ms exceeded".
    const res = await api.post('/api/auth/google', { credential }, { timeout: 30000 })
    const { token: t, user: u } = res.data
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
    queryClient.clear()
    setToken(t)
    setUser(u)
  }, [queryClient])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    queryClient.clear()
    setToken(null)
    setUser(null)
  }, [queryClient])

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

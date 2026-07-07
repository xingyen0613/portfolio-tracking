import axios from 'axios'

const TOKEN_KEY = 'portfolio_token'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 10000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    // 登入 API 自己的 401 是「登入失敗」，要留給 LoginPage 顯示錯誤，不能 reload
    const isLoginRequest = err.config?.url?.includes('/api/auth/google')
    if (err.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('portfolio_user')
      window.location.reload()
    }
    return Promise.reject(err)
  },
)

export async function checkHealth(): Promise<{ status: string }> {
  const res = await api.get('/health')
  return res.data
}

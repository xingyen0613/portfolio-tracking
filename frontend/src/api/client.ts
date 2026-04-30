import axios from 'axios'

export const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 10000,
})

export async function checkHealth(): Promise<{ status: string }> {
  const res = await api.get('/health')
  return res.data
}

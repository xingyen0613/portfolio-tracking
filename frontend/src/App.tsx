import { useQuery } from '@tanstack/react-query'
import { checkHealth } from './api/client'

function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: checkHealth,
  })

  return (
    <div style={{ padding: '32px', color: 'var(--fg1)' }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>
        Portfolio Dashboard
      </h1>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: 'var(--fg2)' }}>
        {isLoading && 'Connecting to API...'}
        {isError && '⚠ Cannot reach backend (localhost:8000)'}
        {data && `✓ API status: ${data.status}`}
      </div>
    </div>
  )
}

export default App

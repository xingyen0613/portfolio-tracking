import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import Shell from './components/Shell'

export default function App() {
  const { token } = useAuth()
  return token ? <Shell /> : <LoginPage />
}

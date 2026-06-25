import { createContext, useCallback, useContext, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface DemoContextType {
  isDemo: boolean
  enterDemo: () => void
  exitDemo: () => void
}

const DemoContext = createContext<DemoContextType | null>(null)

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [isDemo, setIsDemo] = useState(false)

  const enterDemo = useCallback(() => setIsDemo(true), [])
  const exitDemo = useCallback(() => {
    setIsDemo(false)
    queryClient.clear()
  }, [queryClient])

  return (
    <DemoContext.Provider value={{ isDemo, enterDemo, exitDemo }}>
      {children}
    </DemoContext.Provider>
  )
}

export function useDemo() {
  const ctx = useContext(DemoContext)
  if (!ctx) throw new Error('useDemo must be used within DemoProvider')
  return ctx
}

import { createContext, useCallback, useContext, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface DemoContextType {
  isDemo: boolean
  tourActive: boolean
  enterDemo: () => void
  exitDemo: () => void
  endTour: () => void
}

const DemoContext = createContext<DemoContextType | null>(null)

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [isDemo, setIsDemo] = useState(false)
  const [tourActive, setTourActive] = useState(false)

  const enterDemo = useCallback(() => {
    setIsDemo(true)
    setTourActive(true)
  }, [])
  const exitDemo = useCallback(() => {
    setIsDemo(false)
    setTourActive(false)
    queryClient.clear()
  }, [queryClient])
  const endTour = useCallback(() => setTourActive(false), [])

  return (
    <DemoContext.Provider value={{ isDemo, tourActive, enterDemo, exitDemo, endTour }}>
      {children}
    </DemoContext.Provider>
  )
}

export function useDemo() {
  const ctx = useContext(DemoContext)
  if (!ctx) throw new Error('useDemo must be used within DemoProvider')
  return ctx
}

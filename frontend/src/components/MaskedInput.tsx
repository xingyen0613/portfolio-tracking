import { useState } from 'react'
import { Icon } from './Icon'

interface Props {
  className?: string
  placeholder?: string
  value: string
  onChange: (v: string) => void
  disabled?: boolean
}

export default function MaskedInput({ className, placeholder, value, onChange, disabled }: Props) {
  const [visible, setVisible] = useState(false)

  return (
    <div style={{ position: 'relative' }}>
      <input
        className={className}
        type={visible ? 'text' : 'password'}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        style={{ paddingRight: 36 }}
      />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        disabled={disabled}
        title={visible ? 'Hide' : 'Show'}
        style={{
          position: 'absolute',
          right: 8,
          top: '50%',
          transform: 'translateY(-50%)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--fg-3)',
          padding: 4,
          display: 'flex',
          alignItems: 'center',
          lineHeight: 0,
        }}
      >
        <Icon name={visible ? 'eyeOff' : 'eye'} />
      </button>
    </div>
  )
}

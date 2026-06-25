import { useDemo } from '../context/DemoContext'

export default function DemoBanner() {
  const { exitDemo } = useDemo()

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '8px 24px',
      background: 'rgba(124,110,245,0.08)',
      borderBottom: '1px solid rgba(124,110,245,0.2)',
      flexShrink: 0,
    }}>
      <span style={{
        fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
        padding: '2px 7px', borderRadius: 4,
        background: 'rgba(124,110,245,0.18)',
        color: 'var(--accent)',
        textTransform: 'uppercase',
        flexShrink: 0,
      }}>
        展示模式
      </span>
      <span style={{ fontSize: 12, color: 'var(--fg-3)', flex: 1 }}>
        資料均為範例・新增、刪除、編輯等操作不會有實際效果
      </span>
      <button
        onClick={exitDemo}
        style={{
          background: 'transparent',
          border: '1px solid rgba(124,110,245,0.35)',
          borderRadius: 6,
          color: 'var(--accent)',
          fontSize: 11,
          fontWeight: 500,
          padding: '4px 10px',
          cursor: 'pointer',
          flexShrink: 0,
          transition: 'background 120ms',
        }}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(124,110,245,0.12)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        退出展示 →
      </button>
    </div>
  )
}

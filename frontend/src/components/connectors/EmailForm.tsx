import type { SourceTemplate } from '../../data/sourceTemplates'

interface Props {
  template: SourceTemplate
}

/**
 * Email-based brokers (元大 / 富邦) need Gmail OAuth which is owner-only in v1.
 * Render the visual layout but disable interaction.
 */
export default function EmailForm({ template }: Props) {
  return (
    <>
      <div className="field">
        <label className="field-label">連接 Gmail</label>
        <button
          type="button"
          className="btn btn-outline"
          disabled
          style={{ width: '100%', justifyContent: 'center', padding: 14, opacity: 0.6 }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">
            <path d="M21.35 11.1H12v3.2h5.35c-.5 2.4-2.5 3.8-5.35 3.8a5.9 5.9 0 1 1 0-11.8c1.45 0 2.75.5 3.8 1.4l2.4-2.4A9.4 9.4 0 0 0 12 2.6 9.4 9.4 0 1 0 21.35 11.1z" />
          </svg>
          使用 Google 登入（目前僅限管理者）
        </button>
        <div className="field-hint">
          {template.name} 整合需要互動式 Gmail OAuth 授權，目前僅限工作區管理者使用，未來將開放給所有用戶。
        </div>
      </div>

      <div className="field">
        <label className="field-label">郵件篩選條件</label>
        <input
          className="input mono"
          disabled
          defaultValue={`from:${template.id}@${template.id}.com`}
          style={{ opacity: 0.6 }}
        />
      </div>

      <div className="field">
        <label className="field-label">PDF 密碼（如有）</label>
        <input
          className="input mono"
          type="password"
          placeholder="沒有的話請留空"
          disabled
          style={{ opacity: 0.6 }}
        />
      </div>
    </>
  )
}

import { useEffect } from 'react'
import Footer from '../components/Footer'
import GuideContent from '../components/GuideContent'

/** 免登入的圖文使用說明頁，landing page 的「查看完整使用說明」指向這裡。 */
export default function GuidePage() {
  useEffect(() => {
    document.title = '使用說明 · ALL IN'
  }, [])

  return (
    <div className="legal-stage">
      <header className="legal-header">
        <a className="legal-brand" href="/">
          <span className="legal-brand-name">ALL IN</span>
        </a>
        <nav className="legal-nav">
          <a href="/">回首頁</a>
          <a href="/preview/dashboard">預覽模式</a>
        </nav>
      </header>

      <article className="legal-doc guide-doc">
        <h1>使用說明</h1>
        <p className="legal-intro">從連接第一個來源到看懂各項圖表 · 點擊圖片可放大</p>

        <GuideContent />

        <div className="legal-back">
          <a href="/">← 回到 ALL IN</a>
        </div>
      </article>

      <Footer sameTab />
    </div>
  )
}

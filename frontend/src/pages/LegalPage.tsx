import { useEffect } from 'react'
import Footer from '../components/Footer'
import { LEGAL_DOCS, LEGAL_NAV, type LegalSlug } from '../legal/content'

export default function LegalPage({ slug }: { slug: LegalSlug }) {
  const doc = LEGAL_DOCS[slug]

  useEffect(() => {
    document.title = `${doc.title} · ALL IN`
  }, [doc.title])

  return (
    <div className="legal-stage">
      <header className="legal-header">
        <a className="legal-brand" href="/">
          <span className="legal-brand-name">ALL IN</span>
        </a>
        <nav className="legal-nav">
          {LEGAL_NAV.map(item => (
            <a
              key={item.slug}
              href={item.path}
              className={item.slug === slug ? 'is-active' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </header>

      <article className="legal-doc">
        <h1>{doc.title}</h1>
        <div className="legal-updated">最後更新日期：{doc.updated}</div>
        <p className="legal-intro">{doc.intro}</p>

        {doc.sections.map(section => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            {section.blocks.map((block, i) => {
              if (block.t === 'p') return <p key={i}>{block.text}</p>
              if (block.t === 'ul') {
                return (
                  <ul key={i}>
                    {block.items.map((item, j) => (
                      <li key={j}>{item}</li>
                    ))}
                  </ul>
                )
              }
              return (
                <p key={i}>
                  <a
                    className="legal-link"
                    href={block.href}
                    target={block.href.startsWith('http') ? '_blank' : undefined}
                    rel={block.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  >
                    {block.label}
                  </a>
                </p>
              )
            })}
          </section>
        ))}

        <div className="legal-back">
          <a href="/">← 回到 ALL IN</a>
        </div>
      </article>

      <Footer sameTab />
    </div>
  )
}

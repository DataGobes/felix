import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import sql from 'highlight.js/lib/languages/sql'
import java from 'highlight.js/lib/languages/java'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import json from 'highlight.js/lib/languages/json'
import yaml from 'highlight.js/lib/languages/yaml'
import css from 'highlight.js/lib/languages/css'
import r from 'highlight.js/lib/languages/r'
import 'highlight.js/styles/github-dark.min.css'

import katex from 'katex'
import 'katex/dist/katex.min.css'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('java', java)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('csharp', csharp)
hljs.registerLanguage('go', go)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('json', json)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('r', r)

/**
 * Renders a document element based on its type.
 * @param {Object} element - The element data from the backend
 * @param {string} [imageUrl] - Optional direct image URL for picture elements
 *
 * Note: dangerouslySetInnerHTML is used safely here — highlight.js escapes all
 * input and only produces <span> tags, and KaTeX generates its own safe DOM
 * elements from LaTeX syntax. Neither accepts arbitrary HTML.
 */
export default function ElementRenderer({ element, imageUrl }) {
  const text = element.full_text || element.text_preview || ''

  switch (element.element_type) {
    case 'section_header':
      if (element.heading_level === 1)
        return <h2 className="text-xl font-bold text-[#c8e6c8] mt-6 mb-3 first:mt-0">{text}</h2>
      if (element.heading_level === 2)
        return <h3 className="text-lg font-semibold text-[#c8e6c8] mt-5 mb-2">{text}</h3>
      return <h4 className="text-base font-medium text-[#a8d8a8] mt-4 mb-1.5">{text}</h4>

    case 'text':
    case 'paragraph':
      return <p className="text-sm text-[#8ab88a] leading-relaxed mb-3">{text}</p>

    case 'list_item':
      return (
        <div className="flex gap-2 mb-1.5 ml-4">
          <span className="text-[#3d6b3d] shrink-0 mt-0.5">•</span>
          <p className="text-sm text-[#8ab88a] leading-relaxed">{text}</p>
        </div>
      )

    case 'code': {
      const lang = element.metadata?.code_language
      // Strip language identifier line if the ingestion pipeline embedded it
      let codeText = text
      if (lang) {
        const firstLine = codeText.split('\n', 1)[0].trim().toLowerCase()
        if (firstLine === lang.toLowerCase()) {
          codeText = codeText.slice(codeText.indexOf('\n') + 1)
        }
      }
      let highlighted
      if (lang && hljs.getLanguage(lang)) {
        highlighted = hljs.highlight(codeText, { language: lang }).value
      } else {
        highlighted = hljs.highlightAuto(codeText).value
      }
      // highlight.js output is sanitized — it escapes input and only produces <span> tags
      return (
        <div className="my-3 rounded-lg overflow-x-auto border border-[#1a3a1a]">
          {lang && (
            <div className="px-3 py-1 bg-[#0a120a] border-b border-[#1a3a1a] text-[10px] text-[#3d6b3d] font-mono uppercase tracking-wider">
              {lang}
            </div>
          )}
          <pre className="p-3 bg-[#0a120a] text-xs font-mono whitespace-pre leading-relaxed">
            <code dangerouslySetInnerHTML={{ __html: highlighted }} />
          </pre>
        </div>
      )
    }

    case 'formula': {
      let html
      try {
        // KaTeX output is sanitized — it generates its own safe DOM elements from LaTeX
        html = katex.renderToString(text, { throwOnError: false, displayMode: true })
      } catch {
        html = null
      }
      return html ? (
        <div
          className="my-4 p-4 bg-[#060d06]/50 rounded-lg border border-[#1a3a1a] overflow-x-auto text-center"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <div className="my-3 p-3 bg-[#0a120a] rounded-lg overflow-x-auto border border-[#1a3a1a]">
          <pre className="text-xs text-amber-300 font-mono whitespace-pre leading-relaxed">{text}</pre>
        </div>
      )
    }

    case 'picture':
      if (imageUrl) {
        return (
          <div className="my-4">
            <img
              src={imageUrl}
              alt={element.caption || 'Image'}
              className="max-w-full rounded-lg border border-[#1a3a1a]"
            />
            {element.caption && <p className="text-xs text-[#5a8a5a] italic mt-1">{element.caption}</p>}
          </div>
        )
      }
      return (
        <div className="my-4 py-8 border border-dashed border-[#1a3a1a] rounded-lg text-sm text-[#3d6b3d] text-center bg-[#0a120a]/30">
          ▣ Image
        </div>
      )

    case 'caption':
      return <p className="text-xs text-[#5a8a5a] italic mb-3 -mt-2">{text}</p>

    case 'footnote':
      return (
        <p className="text-xs text-[#3d6b3d] border-t border-[#0d2b0d] pt-2 mt-4 mb-2">
          <span className="text-[#2a4a2a] mr-1">†</span>{text}
        </p>
      )

    case 'page_header':
    case 'page_footer':
      return null

    case 'group':
      return (
        <div className="my-2 pl-3 border-l-2 border-[#1a3a1a]">
          {text && <p className="text-sm text-[#8ab88a] leading-relaxed mb-2">{text}</p>}
        </div>
      )

    default:
      if (!text) return null
      return <p className="text-sm text-[#5a8a5a] mb-2">{text}</p>
  }
}

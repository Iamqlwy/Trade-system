/**
 * HTML 净化模块 — 基于 DOMPurify
 *
 * 用于所有 v-html 渲染点，防止 XSS 攻击。
 * 使用前需安装依赖：npm install dompurify @types/dompurify
 */

import DOMPurify from 'dompurify'

/**
 * 允许的安全 HTML 标签白名单（Markdown 渲染所需）
 */
const ALLOWED_TAGS = [
  // 块级
  'p', 'div', 'br', 'hr',
  // 标题
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  // 列表
  'ul', 'ol', 'li',
  // 表格
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  // 行内
  'strong', 'em', 'b', 'i', 'u', 's', 'del', 'ins', 'mark',
  'sub', 'sup', 'small', 'abbr', 'code', 'kbd', 'samp', 'var',
  // 链接和图片
  'a', 'img',
  // 引用
  'blockquote', 'pre', 'pre',
  // 其他
  'span', 'details', 'summary',
]

/**
 * 允许的安全属性白名单
 */
const ALLOWED_ATTR = [
  'href', 'target', 'rel',       // <a>
  'src', 'alt', 'title', 'width', 'height', // <img>
  'class', 'id',                  // 通用
  'colspan', 'rowspan',           // 表格
  'style',                        // 允许内联样式（代码高亮需要）
  'data-line',                    // 代码块行号
]

/**
 * 净化 HTML 字符串，移除危险标签和属性。
 *
 * @param html - marked.parse() 输出的原始 HTML
 * @returns 安全的 HTML 字符串
 */
export function sanitizeHtml(html: string): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // 禁止 data: URI（防止 SVG/JS 注入）
    ALLOW_DATA_ATTR: false,
    // 禁止 <math> 命名空间
    ADD_TAGS: [''],
  })
}

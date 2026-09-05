/**
 * 输入校验与清理工具
 */

/**
 * 股票代码格式校验（A 股格式：6 位数字，可选 .SH/.SZ 后缀）
 */
const STOCK_CODE_RE = /^\d{6}(\.(SH|SZ))?$/i

export function isValidStockCode(code: string): boolean {
  return STOCK_CODE_RE.test(code.trim())
}

/**
 * 清理用户输入文本：
 * - 移除控制字符（保留换行和制表符）
 * - 可选截断到指定长度
 *
 * @param text - 原始输入
 * @param maxLength - 最大长度（默认 10000）
 * @returns 清理后的文本
 */
export function cleanInput(text: string, maxLength: number = 10000): string {
  if (!text) return ''
  // 移除控制字符（保留 \n \r \t）
  let cleaned = text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '')
  // 截断
  if (cleaned.length > maxLength) {
    cleaned = cleaned.slice(0, maxLength)
  }
  return cleaned
}

/**
 * 清理单行文本输入（额外折叠空白和换行）
 */
export function cleanSingleLineInput(text: string, maxLength: number = 200): string {
  if (!text) return ''
  let cleaned = cleanInput(text, maxLength)
  // 折叠换行和多余空白
  cleaned = cleaned.replace(/\s+/g, ' ').trim()
  if (cleaned.length > maxLength) {
    cleaned = cleaned.slice(0, maxLength)
  }
  return cleaned
}

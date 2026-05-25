/**
 * AuditLog 辅助函数集合
 * 从 AuditLogViewer 组件中提取的纯函数和 React 渲染辅助函数
 *
 * 整合了四个核心工具：
 * - getNestedValue: 从嵌套对象按路径提取值
 * - formatTimestamp: 格式化时间戳为可读字符串
 * - renderCellValue: 根据列名渲染单元格值
 * - renderStatusBadge: 渲染日志级别和 HTTP 状态码的彩色徽章
 */

import type { CSSProperties } from 'react'
import React from 'react'
import { tokens } from '@fluentui/react-components'

// 从已有工具模块重新导出的纯函数
export { getNestedValue } from './getNestedValue'
export { formatTimestamp } from './formatTimestamp'
export { renderCellValue } from './renderCellValue'

/**
 * Status Badge 样式，使用 Fluent UI tokens 保持与组件一致的视觉风格
 */
const badgeStyles: Record<string, CSSProperties> = {
  info: {
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground2,
    padding: '2px 8px',
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: String(tokens.fontWeightSemibold),
  },
  warning: {
    backgroundColor: tokens.colorStatusWarningBackground2,
    color: tokens.colorStatusWarningForeground2,
    padding: '2px 8px',
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: String(tokens.fontWeightSemibold),
  },
  error: {
    backgroundColor: tokens.colorStatusDangerBackground2,
    color: tokens.colorStatusDangerForeground2,
    padding: '2px 8px',
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: String(tokens.fontWeightSemibold),
  },
  success: {
    backgroundColor: tokens.colorStatusSuccessBackground2,
    color: tokens.colorStatusSuccessForeground2,
    padding: '2px 8px',
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: String(tokens.fontWeightSemibold),
  },
}

/**
 * 渲染日志级别和 HTTP 状态码的颜色徽章
 * 从 AuditLogViewer 组件中提取，保持相同的行为
 *
 * @param value - 单元格显示值
 * @param columnName - 列名（'level' 或 'http_status_code'）
 * @returns React 元素（彩色 <span> 徽章或 null）
 */
export function renderStatusBadge(
  value: string,
  columnName: string
): React.ReactElement | null {
  if (columnName === 'level') {
    const level = value.toUpperCase()
    if (level === 'ERROR' || level === 'CRITICAL') {
      return <span style={badgeStyles.error}>{value}</span>
    }
    if (level === 'WARNING' || level === 'WARN') {
      return <span style={badgeStyles.warning}>{value}</span>
    }
    return <span style={badgeStyles.info}>{value}</span>
  }
  if (columnName === 'http_status_code') {
    const code = parseInt(value, 10)
    if (code >= 200 && code < 300) {
      return <span style={badgeStyles.success}>{value}</span>
    }
    if (code >= 400) {
      return <span style={badgeStyles.error}>{value}</span>
    }
    return <span>{value}</span>
  }
  return null
}

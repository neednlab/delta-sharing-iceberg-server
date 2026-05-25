import { formatTimestamp } from './formatTimestamp';

/** 需要委托 formatTimestamp 进行时间戳格式化的列名集合 */
const TIMESTAMP_COLUMNS = new Set(['timestamp', 'time']);

/** 需要使用更长截断长度（200 字符）的列名及其最大长度 */
const LONG_TEXT_COLUMN_MAX_LENGTHS: Record<string, number> = {
  query_object: 200,
  client_user_agent: 200,
};

/**
 * 渲染单元格值
 * 根据列名进行特殊格式化：timestamp 显示可读日期，长字符串截断
 *
 * @param value - 原始值
 * @param columnName - 列名
 * @param maxLength - 最大显示长度，默认 100 字符
 * @returns 格式化后的显示字符串
 */
export function renderCellValue(
  value: unknown,
  columnName: string,
  maxLength: number = 100
): string {
  if (value === null || value === undefined) return '-';
  if (TIMESTAMP_COLUMNS.has(columnName)) {
    return formatTimestamp(value);
  }
  if (typeof value === 'object') {
    try {
      const json = JSON.stringify(value);
      return json.length > maxLength ? json.substring(0, maxLength) + '...' : json;
    } catch {
      return '[Object]';
    }
  }
  const str = String(value);
  const effectiveMaxLength = LONG_TEXT_COLUMN_MAX_LENGTHS[columnName] ?? maxLength;
  return str.length > effectiveMaxLength
    ? str.substring(0, effectiveMaxLength) + '...'
    : str;
}

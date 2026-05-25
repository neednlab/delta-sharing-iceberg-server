/**
 * 日期格式化工具函数
 * 接受Unix秒级时间戳（number或string），返回locale格式化字符串
 * 对无效/零值时间戳返回 "-"
 *
 * 内部委托 formatTimestamp 进行格式化，消除时间戳解析逻辑的代码重复
 */
import { formatTimestamp } from './formatTimestamp';

export function formatDate(timestamp: number | string): string {
  const ts = typeof timestamp === 'string' ? Number(timestamp) : timestamp;
  if (isNaN(ts) || ts <= 0) return '-';
  return formatTimestamp(ts * 1000);
}

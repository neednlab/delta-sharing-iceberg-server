/**
 * 格式化时间戳为可读日期字符串
 * 支持 Unix 毫秒时间戳、秒时间戳、ISO 字符串等多种格式
 *
 * 使用 Number() 替代 parseInt() 以正确拒收含非数字字符的字符串（如 "123abc"）
 *
 * @param ts - 时间戳值（数字、字符串或 undefined）
 * @returns 格式化后的日期时间字符串，解析失败则返回 "-"
 */
export function formatTimestamp(ts: unknown): string {
  if (ts === null || ts === undefined) return '-';
  let timestamp: number;
  if (typeof ts === 'string') {
    const parsed = Date.parse(ts);
    if (!isNaN(parsed)) {
      return new Date(parsed).toLocaleString();
    }
    const num = Number(ts);
    if (Number.isNaN(num) || !Number.isFinite(num)) return '-';
    timestamp = num;
  } else if (typeof ts === 'number') {
    timestamp = ts;
  } else {
    return '-';
  }
  if (Number.isNaN(timestamp) || !Number.isFinite(timestamp) || timestamp <= 0) return '-';
  if (timestamp > 1e12) {
    return new Date(timestamp).toLocaleString();
  }
  return new Date(timestamp * 1000).toLocaleString();
}

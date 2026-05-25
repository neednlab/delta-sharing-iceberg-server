/**
 * 从嵌套对象中按点号分隔的路径获取值
 * 例如 getNestedValue({http: {method: "GET"}}, "http.method") => "GET"
 *
 * @param obj - 源对象（可以是任意嵌套结构）
 * @param path - 点号分隔的路径字符串
 * @returns 字符串形式的值，如果路径不存在则返回 "-"
 */
export function getNestedValue(obj: unknown, path: string): string {
  if (obj === null || obj === undefined) return '-';
  const keys = path.split('.');
  let current: unknown = obj;
  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return '-';
    }
    current = (current as Record<string, unknown>)[key];
  }
  if (current === null || current === undefined) return '-';
  if (typeof current === 'object') {
    try {
      return JSON.stringify(current);
    } catch {
      return '[Object]';
    }
  }
  return String(current);
}

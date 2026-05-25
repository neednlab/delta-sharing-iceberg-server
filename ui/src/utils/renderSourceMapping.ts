/**
 * 格式化 Source Mapping 显示文本
 * Schema 行：显示 {metastore_db}（metastore_db 为空时 fallback 到 fallbackSchemaName）
 * Table 行：显示 {effective_db}.{metastore_table}（null-safe，db 为空时 fallback 到 fallbackSchemaName）
 * 两者均为空时显示 '-'
 *
 * @param metastoreDb - Metastore 数据库名
 * @param metastoreTable - Metastore 表名（可选）
 * @param isSchema - 是否为 Schema 类型
 * @param fallbackSchemaName - 回退 Schema 名称（可选）
 * @returns 格式化后的 Source Mapping 显示文本
 */
export function renderSourceMapping(
  metastoreDb: string,
  metastoreTable?: string,
  isSchema: boolean = false,
  fallbackSchemaName?: string
): string {
  const effectiveDb = metastoreDb || fallbackSchemaName || '';
  if (!effectiveDb) return '-';
  if (isSchema) return effectiveDb;
  if (metastoreTable) return `${effectiveDb}.${metastoreTable}`;
  return effectiveDb;
}

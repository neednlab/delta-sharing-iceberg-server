/**
 * Token 过期时间计算工具
 * 将过期选项（7 days/30 days/90 days/No expiration/Custom）转换为小时数
 *
 * @param option - 过期选项字符串
 * @param customDate - 自定义日期（仅 option 为 "Custom" 时使用）
 * @returns 过期小时数，No expiration 返回 0，无效选项或无自定义日期时返回 undefined
 */

export function calculateExpirationHours(
  option: string,
  customDate?: Date
): number | undefined {
  if (option === '7 days') {
    return 7 * 24;
  } else if (option === '30 days') {
    return 30 * 24;
  } else if (option === '90 days') {
    return 90 * 24;
  } else if (option === 'No expiration') {
    return 0;
  } else if (option === 'Custom' && customDate) {
    const now = new Date();
    const diffMs = customDate.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60)));
  }
  return undefined;
}

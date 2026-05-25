/**
 * 根据 Token 创建时间和轮换周期计算 Token 年龄状态
 *
 * @param createdAt - Token 创建时间（Unix 秒级时间戳）
 * @param rotationPeriodHours - 轮换周期（小时）
 * @returns 包含 label 和 color 的状态对象
 */
export function tokenAgeStatus(
  createdAt: number,
  rotationPeriodHours: number
): { label: string; color: 'success' | 'warning' | 'danger' } {
  const now = Date.now() / 1000;
  const ageHours = (now - createdAt) / 3600;

  if (ageHours < rotationPeriodHours) {
    return { label: 'Active', color: 'success' };
  } else if (ageHours < 2 * rotationPeriodHours) {
    return { label: 'Rotation Recommended', color: 'warning' };
  } else {
    return { label: 'Rotation Overdue', color: 'danger' };
  }
}

import type { Recipient } from '../types';

/**
 * 从 Recipient 对象获取显示名称
 * 优先使用 recipient_name 字段，回退到 name 字段，最终回退到空字符串
 *
 * @param recipient - Recipient 对象
 * @returns 显示名称字符串
 */
export function getRecipientDisplayName(recipient: Recipient): string {
  return recipient.recipient_name || recipient.name || '';
}

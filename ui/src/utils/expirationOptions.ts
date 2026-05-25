/**
 * Token 过期选项常量数组
 * 用于 Dropdown 组件的 <Option> 渲染
 */
export const EXPIRATION_OPTIONS = [
  { value: '7 days', label: '7 days' },
  { value: '30 days', label: '30 days' },
  { value: '90 days', label: '90 days' },
  { value: 'No expiration', label: 'No expiration' },
  { value: 'Custom', label: 'Custom' },
] as const;

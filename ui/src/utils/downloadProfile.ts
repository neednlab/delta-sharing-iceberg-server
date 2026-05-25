import type { ProfileContent } from '../types';

/**
 * 在浏览器中触发 Profile 文件的 JSON 下载
 * 通过 Blob + URL.createObjectURL + 临时 <a> 元素实现下载
 * 发生 DOM 异常时静默忽略（不抛异常，不阻塞调用方）
 *
 * 注意：仅可在浏览器环境调用，依赖 DOM API
 *
 * @param profileContent - Profile 文件内容对象
 * @param fileName - 下载文件名
 */
export function downloadProfile(profileContent: ProfileContent, fileName: string): void {
  try {
    const blob = new Blob([JSON.stringify(profileContent, null, 2)], {
      type: 'application/json',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch {
    // profile 下载失败不影响主流程
  }
}

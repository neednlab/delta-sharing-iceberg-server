import { describe, it, expect } from 'vitest'
import { getNestedValue, formatTimestamp, renderCellValue } from '../../utils/auditLogHelpers'

describe('getNestedValue', () => {
  describe('正常嵌套路径', () => {
    it('应按点号分隔的路径提取嵌套值', () => {
      expect(getNestedValue({ http: { method: 'GET' } }, 'http.method')).toBe('GET')
    })

    it('应提取深层嵌套值', () => {
      expect(
        getNestedValue({ a: { b: { c: 'deep' } } }, 'a.b.c')
      ).toBe('deep')
    })
  })

  describe('缺失路径', () => {
    it('应返回 "-" 当路径不存在', () => {
      expect(getNestedValue({ http: {} }, 'http.method')).toBe('-')
    })

    it('应返回 "-" 当中间路径不存在', () => {
      expect(getNestedValue({}, 'a.b.c')).toBe('-')
    })
  })

  describe('null/undefined 对象', () => {
    it('应返回 "-" 当对象为 null', () => {
      expect(getNestedValue(null, 'http.method')).toBe('-')
    })

    it('应返回 "-" 当对象为 undefined', () => {
      expect(getNestedValue(undefined, 'http.method')).toBe('-')
    })
  })

  describe('对象值序列化', () => {
    it('应序列化嵌套对象为 JSON 字符串', () => {
      const result = getNestedValue({ http: { headers: { 'Content-Type': 'json' } } }, 'http.headers')
      expect(result).toBe('{"Content-Type":"json"}')
    })
  })
})

describe('formatTimestamp', () => {
  describe('毫秒时间戳', () => {
    it('应返回格式化的日期字符串', () => {
      const result = formatTimestamp(1714233600000)
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })
  })

  describe('秒时间戳', () => {
    it('应返回格式化的日期字符串', () => {
      const result = formatTimestamp(1714233600)
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })
  })

  describe('null 输入', () => {
    it('应返回 "-"', () => {
      expect(formatTimestamp(null)).toBe('-')
    })
  })

  describe('undefined 输入', () => {
    it('应返回 "-"', () => {
      expect(formatTimestamp(undefined)).toBe('-')
    })
  })

  describe('ISO 日期字符串', () => {
    it('应返回格式化的日期字符串', () => {
      const result = formatTimestamp('2024-04-27T20:00:00.000Z')
      expect(result).not.toBe('-')
    })
  })

  describe('无效值', () => {
    it('应返回 "-" 当输入为 0', () => {
      expect(formatTimestamp(0)).toBe('-')
    })

    it('应返回 "-" 当输入为负数', () => {
      expect(formatTimestamp(-1)).toBe('-')
    })
  })
})

describe('renderCellValue', () => {
  describe('普通值渲染', () => {
    it('应返回字符串形式的值', () => {
      expect(renderCellValue('hello', 'some_column')).toBe('hello')
    })

    it('应返回数字的字符串形式', () => {
      expect(renderCellValue(42, 'count')).toBe('42')
    })
  })

  describe('长字符串截断', () => {
    it('应截断超过 maxLength 的字符串并添加省略号', () => {
      const longStr = 'a'.repeat(200)
      const result = renderCellValue(longStr, 'message', 100)
      expect(result).toHaveLength(103) // 100 char + '...'
      expect(result).toMatch(/\.{3}$/)
    })
  })

  describe('timestamp 列特殊格式化', () => {
    it('timestamp 列名应调用 formatTimestamp 格式化', () => {
      const result = renderCellValue(1714233600000, 'timestamp')
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })

    it('time 列名也应调用 formatTimestamp 格式化', () => {
      const result = renderCellValue(1714233600000, 'time')
      expect(result).not.toBe('-')
      expect(result).toContain('2024')
    })
  })

  describe('null/undefined 值', () => {
    it('应返回 "-" 当值为 null', () => {
      expect(renderCellValue(null, 'some_column')).toBe('-')
    })

    it('应返回 "-" 当值为 undefined', () => {
      expect(renderCellValue(undefined, 'some_column')).toBe('-')
    })
  })

  describe('对象值 JSON 序列化', () => {
    it('应序列化对象为 JSON 字符串', () => {
      expect(renderCellValue({ key: 'val' }, 'metadata')).toBe('{"key":"val"}')
    })

    it('应截断过长的 JSON 字符串', () => {
      const bigObj: Record<string, number> = {}
      for (let i = 0; i < 200; i++) {
        bigObj[`key${i}`] = i
      }
      const result = renderCellValue(bigObj, 'data', 100)
      expect(result.length).toBe(103)
      expect(result).toMatch(/\.{3}$/)
    })
  })
})

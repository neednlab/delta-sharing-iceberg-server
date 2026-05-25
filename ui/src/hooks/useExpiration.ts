/**
 * Token 过期选项状态管理Hook
 * 封装过期选项和自定义日期的状态管理，并提供计算后的过期小时数
 *
 * @returns 过期状态和操作方法
 */

import { useState, useMemo } from 'react';
import { calculateExpirationHours } from '../utils/calculateExpirationHours';

interface UseExpirationReturn {
  expirationHours: number | undefined;
  expirationOption: string;
  setExpirationOption: (option: string) => void;
  customExpirationDate: Date | undefined;
  setCustomExpirationDate: (date: Date | undefined) => void;
}

export function useExpiration(
  initialOption: string = '30 days'
): UseExpirationReturn {
  const [expirationOption, setExpirationOptionRaw] = useState(initialOption);
  const [customExpirationDate, setCustomExpirationDate] = useState<
    Date | undefined
  >(undefined);

  const setExpirationOption = (option: string) => {
    setExpirationOptionRaw(option);
    if (option !== 'Custom') {
      setCustomExpirationDate(undefined);
    }
  };

  const expirationHours = useMemo(
    () => calculateExpirationHours(expirationOption, customExpirationDate),
    [expirationOption, customExpirationDate]
  );

  return {
    expirationHours,
    expirationOption,
    setExpirationOption,
    customExpirationDate,
    setCustomExpirationDate,
  };
}

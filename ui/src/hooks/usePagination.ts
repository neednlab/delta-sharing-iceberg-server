/**
 * 通用分页Hook
 * 封装分页状态（当前页、下一页Token、加载/错误状态）和导航处理器
 *
 * @template T - 列表项类型
 * @param fetchFn - 数据获取函数，接收分页参数，返回包含items和nextPageToken的Promise
 * @param maxResults - 每页最大条目数
 * @returns 分页状态和操作方法
 */

import { useState, useCallback, useEffect, useRef } from 'react';

interface PaginationParams {
  maxResults?: number;
  pageToken?: string;
}

interface PaginatedResult<T> {
  items: T[];
  next_page_token?: string;
}

interface UsePaginationReturn<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  currentPage: number;
  nextPageToken: string | undefined;
  goNext: () => void;
  goPrev: () => void;
  reload: () => void;
}

export function usePagination<T>(
  fetchFn: (params: PaginationParams) => Promise<PaginatedResult<T>>,
  maxResults: number = 20
): UsePaginationReturn<T> {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [nextPageToken, setNextPageToken] = useState<string | undefined>();

  const abortRef = useRef<AbortController>(undefined);
  const fetchFnRef = useRef(fetchFn);

  useEffect(() => {
    fetchFnRef.current = fetchFn;
  });

  const load = useCallback(
    async (params?: PaginationParams) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const response = await fetchFnRef.current({
          maxResults,
          ...params,
        });

        if (controller.signal.aborted) return;

        setItems(response.items || []);
        setNextPageToken(response.next_page_token);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [maxResults]
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    return () => {
      abortRef.current?.abort();
    };
  }, [load]);

  const goNext = useCallback(() => {
    if (nextPageToken) {
      setCurrentPage((prev) => prev + 1);
      load({ pageToken: nextPageToken });
    }
  }, [nextPageToken, load]);

  const goPrev = useCallback(() => {
    if (currentPage > 1) {
      setCurrentPage((prev) => prev - 1);
      load();
    }
  }, [currentPage, load]);

  const reload = useCallback(() => {
    setCurrentPage(1);
    setNextPageToken(undefined);
    load();
  }, [load]);

  return {
    items,
    loading,
    error,
    currentPage,
    nextPageToken,
    goNext,
    goPrev,
    reload,
  };
}

/**
 * Audit Log Viewer Component
 * 审计日志查看器，支持 admin_audit / client_audit / app 三种日志类型的查看、分页和过滤
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  Button,
  Spinner,
  MessageBar,
  MessageBarBody,
  makeStyles,
  tokens,
  Dropdown,
  Option,
  Input,
  Tooltip,
} from '@fluentui/react-components';
import {
  DismissRegular,
  ChevronLeftRegular,
  ChevronRightRegular,
  DocumentSearchRegular,
  CalendarRegular,
  FilterRegular,
  ChevronDownRegular,
  SearchRegular,
} from '@fluentui/react-icons';
import { mergeClasses } from '@fluentui/react-components';
import type { AuditLogEntry } from '../types';
import { auditLogApi } from '../services/api';
import { getNestedValue, renderCellValue, renderStatusBadge } from '../utils/auditLogHelpers';

/**
 * 已知日志类型对应的默认列顺序
 * 用于动态列渲染时的优先级排序
 */
const LOG_TYPE_COLUMNS: Record<string, string[]> = {
  admin_audit: [
    'timestamp',
    'operation',
    'http.method',
    'http.path',
    'http.status_code',
    'http.duration_ms',
    'error.message',
  ],
  client_audit: [
    'request_id',
    'timestamp',
    'recipient_id',
    'operation',
    'http_status_code',
    'client_ip',
    'client_user_agent',
    'query_object',
    'files_returned',
  ],
  app: ['time', 'level', 'message', 'module', 'function', 'line', 'request_id'],
};

/**
 * client_audit 扁平列名到源字段的映射
 * 后端已展平嵌套字段，所有字段均为顶层属性
 */
const COLUMN_SOURCE_MAP: Record<string, string> = {
  request_id: 'request_id',
  timestamp: 'timestamp',
  recipient_id: 'recipient_id',
  operation: 'operation',
  http_status_code: 'http_status_code',
  client_ip: 'client_ip',
  client_user_agent: 'client_user_agent',
  query_object: 'query_object',
  files_returned: 'files_returned',
};

/**
 * 日志类型的中文标签映射
 * 用于下拉选项的显示文本
 */
const LOG_TYPE_LABELS: Record<string, string> = {
  admin_audit: 'Admin Audit',
  client_audit: 'Client Audit',
  app: 'App Log',
};

/**
 * 页面大小选项
 */
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

/**
 * 组件样式
 */
const useStyles = makeStyles({
  container: {
    padding: tokens.spacingHorizontalL,
  },
  card: {
    backgroundColor: tokens.colorNeutralBackground1,
    borderRadius: tokens.borderRadiusXLarge,
    boxShadow: tokens.shadow8,
    overflow: 'hidden',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: `${tokens.spacingVerticalL} ${tokens.spacingHorizontalXL}`,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  title: {
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground1,
  },
  entryCount: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3,
    marginLeft: tokens.spacingHorizontalM,
  },
  toolbar: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: tokens.spacingHorizontalM,
    padding: `${tokens.spacingVerticalL} ${tokens.spacingHorizontalXL}`,
    flexWrap: 'wrap',
  },
  toolbarLeft: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: tokens.spacingHorizontalM,
    flexWrap: 'wrap',
  },
  toolbarRight: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: tokens.spacingHorizontalM,
    flexWrap: 'wrap',
  },
  toolbarItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: tokens.spacingVerticalXS,
  },
  toolbarLabel: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground2,
  },
  activeFilterTag: {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacingHorizontalXS,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground2,
    borderRadius: tokens.borderRadiusMedium,
    fontSize: tokens.fontSizeBase200,
  },
  tableWrapper: {
    overflowX: 'auto',
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    minWidth: '800px',
  },
  tableHeaderCell: {
    textAlign: 'center',
    position: 'sticky',
    top: 0,
    backgroundColor: tokens.colorNeutralBackground3,
    fontWeight: tokens.fontWeightSemibold,
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground2,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalS}`,
    zIndex: 1,
    whiteSpace: 'nowrap',
    borderBottom: `2px solid ${tokens.colorNeutralStroke2}`,
    '& > div, & > button, & > span': {
      justifyContent: 'center',
      textAlign: 'center',
      width: '100%',
    },
  },
  tableRow: {
    borderBottom: `1px solid ${tokens.colorNeutralStroke1}`,
    '&:hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  tableRowEven: {
    backgroundColor: tokens.colorNeutralBackground2,
    borderBottom: `1px solid ${tokens.colorNeutralStroke1}`,
    '&:hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  tableCell: {
    maxWidth: '200px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'center',
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalS}`,
    fontSize: tokens.fontSizeBase200,
  },
  pagination: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: tokens.spacingHorizontalM,
    padding: `${tokens.spacingVerticalL} ${tokens.spacingHorizontalXL}`,
  },
  errorBar: {
    margin: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalXL}`,
  },
  spinnerContainer: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    padding: tokens.spacingVerticalXXL,
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    padding: tokens.spacingVerticalXXL,
    color: tokens.colorNeutralForeground3,
    gap: tokens.spacingVerticalM,
  },
  paginationButton: {
    fontSize: '12px',
    paddingTop: '4px',
    paddingBottom: '4px',
    paddingLeft: '4px',
    paddingRight: '4px',
    width: '98px',
    height: '30px',
  },
  paginationIcon: {
    fontSize: '18px',
  },
  paginationContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  pageIndicator: {
    marginLeft: '20px',
    marginRight: '20px',
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground2,
  },
  filterInput: {
    width: '200px',
  },
  pageSizeSelector: {
    width: '100px',
  },
  infoText: {
    color: tokens.colorNeutralForeground3,
    fontSize: tokens.fontSizeBase200,
  },
  levelBadgeInfo: {
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground2,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
  },
  levelBadgeWarning: {
    backgroundColor: tokens.colorStatusWarningBackground2,
    color: tokens.colorStatusWarningForeground2,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
  },
  levelBadgeError: {
    backgroundColor: tokens.colorStatusDangerBackground2,
    color: tokens.colorStatusDangerForeground2,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
  },
  statusBadgeSuccess: {
    backgroundColor: tokens.colorStatusSuccessBackground2,
    color: tokens.colorStatusSuccessForeground2,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
  },
  statusBadgeError: {
    backgroundColor: tokens.colorStatusDangerBackground2,
    color: tokens.colorStatusDangerForeground2,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusSmall,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
  },
  // 表头单元格内容容器，用于放置列名和下拉箭头
  headerCellContent: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: tokens.spacingHorizontalXXS,
    cursor: 'pointer',
    userSelect: 'none',
  },
  // 下拉箭头图标样式
  chevronIcon: {
    fontSize: '12px',
    color: tokens.colorNeutralForeground3,
    transition: 'transform 0.2s ease',
  },
  chevronIconOpen: {
    transform: 'rotate(180deg)',
  },
  // 列筛选下拉面板样式（默认居中，首列通过内联样式覆盖为左对齐）
  filterPopover: {
    position: 'absolute',
    top: '100%',
    left: '50%',
    transform: 'translateX(-50%)',
    marginTop: '4px',
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
    boxShadow: tokens.shadow16,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    zIndex: 10,
    minWidth: '220px',
  },
  filterPopoverLeftAlign: {
    left: '0',
    transform: 'none',
  },
  filterPopoverHeader: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground1,
    marginBottom: tokens.spacingVerticalS,
  },
  filterPopoverInput: {
    width: '100%',
  },
  filterPopoverInputOverrides: {
    '& .fui-Input': {
      outline: 'none !important',
      boxShadow: 'none !important',
      border: `1px solid ${tokens.colorNeutralStroke1} !important`,
    },
    '& .fui-Input:focus, & .fui-Input:focus-within': {
      outline: 'none !important',
      boxShadow: 'none !important',
      border: `1px solid ${tokens.colorNeutralStroke1} !important`,
    },
    '& .fui-Input__input': {
      outline: 'none !important',
      boxShadow: 'none !important',
    },
    '& .fui-Input__input:focus': {
      outline: 'none !important',
      boxShadow: 'none !important',
    },
  },
  // 表头单元格相对定位容器，用于下拉面板绝对定位
  headerCellContainer: {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  // 筛选下拉面板固定定位，避免被父级 overflow 裁剪
  filterPopoverFixed: {
    position: 'fixed',
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
    boxShadow: tokens.shadow16,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    zIndex: 1000,
    minWidth: '220px',
  },
});

/**
 * 根据扁平列名从原始日志条目中提取值
 * 对于 client_audit 类型，通过 COLUMN_SOURCE_MAP 映射到顶层字段
 *
 * @param entry - 原始日志条目（JSON 对象）
 * @param col - 扁平列名
 * @returns 提取的值，不存在时为 null
 */
function extractValue(entry: Record<string, unknown>, col: string): unknown {
  const sourcePath = COLUMN_SOURCE_MAP[col];
  if (sourcePath) {
    return getNestedValue(entry, sourcePath);
  }
  return (entry as Record<string, unknown>)[col];
}



/**
 * 审计日志查看器组件
 * 支持三种日志类型的切换、按日期查看、分页浏览和列过滤
 */
export const AuditLogViewer: React.FC = () => {
  const styles = useStyles();

  // 日志类型
  const [logType, setLogType] = useState<'admin_audit' | 'client_audit' | 'app'>('admin_audit');
  // 当前日志类型下可用的日期列表
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  // 所有日志类型的日期数据（用于类型切换时直接使用缓存）
  const [allDates, setAllDates] = useState<Record<string, string[]>>({});
  // 当前选中的日期
  const [selectedDate, setSelectedDate] = useState<string>('');
  // 当前页的日志条目
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // 日期列表加载状态
  const [loadingDates, setLoadingDates] = useState(false);
  // 错误信息
  const [error, setError] = useState<string | null>(null);
  // 分页信息
  const [pagination, setPagination] = useState({
    page: 1,
    pageSize: 50,
    total: 0,
    totalPages: 0,
  });
  // 列级别过滤条件（已提交，触发搜索）：Record<列名, 搜索关键字>
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  // 列级别过滤草稿（用户正在输入中，不触发搜索）
  const [draftFilters, setDraftFilters] = useState<Record<string, string>>({});
  // 当前打开的列筛选下拉面板列名，null 表示没有打开的面板
  const [openFilterColumn, setOpenFilterColumn] = useState<string | null>(null);
  // 用于点击外部关闭下拉面板
  const filterPopoverRef = useRef<HTMLDivElement>(null);
  // 存储每个表头单元格的引用，用于固定定位计算
  const headerCellRefs = useRef<Record<string, HTMLDivElement | null>>({});
  // 筛选面板的固定定位坐标
  const [filterPopoverPos, setFilterPopoverPos] = useState<{ top: number; left: number } | null>(null);

  /**
   * 加载所有日志类型的可用日期列表
   * 在组件挂载时调用一次
   */
  const loadDateList = useCallback(async () => {
    setLoadingDates(true);
    try {
      const response = await auditLogApi.getLogFiles();
      const dates: Record<string, string[]> = {
        admin_audit: (response.admin_audit || []).sort((a, b) => b.localeCompare(a)),
        client_audit: (response.client_audit || []).sort((a, b) => b.localeCompare(a)),
        app: (response.app || []).sort((a, b) => b.localeCompare(a)),
      };
      setAllDates(dates);
      const currentDates = dates[logType] || [];
      setAvailableDates(currentDates);
      if (currentDates.length > 0) {
        setSelectedDate(currentDates[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load log date list');
    } finally {
      setLoadingDates(false);
    }
  }, [logType]);

  /**
   * 加载指定类型的日志条目
   * 根据当前选定的日志类型、日期、分页和过滤条件查询
   */
  const loadEntries = useCallback(async () => {
    if (!selectedDate) return;
    setLoading(true);
    setError(null);
    try {
      // 过滤掉空值的过滤条件，序列化为JSON字符串传给后端
      const activeFilters: Record<string, string> = {};
      for (const [col, val] of Object.entries(columnFilters)) {
        if (val.trim()) {
          activeFilters[col] = val.trim();
        }
      }
      const response = await auditLogApi.getLogEntries(logType, {
        date: selectedDate,
        page: pagination.page,
        page_size: pagination.pageSize,
        filters: Object.keys(activeFilters).length > 0 ? JSON.stringify(activeFilters) : undefined,
      });
      setEntries(response.entries || []);
      setPagination(prev => ({
        ...prev,
        total: response.total,
        totalPages: response.total_pages,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load log entries');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [logType, selectedDate, pagination.page, pagination.pageSize, columnFilters]);

  // 初始加载日期列表 - 仅在组件挂载时执行一次
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadDateList();
  }, [loadDateList]);

  // 日志类型切换时更新可用日期并重置选择
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    if (allDates[logType]) {
      const dates = allDates[logType];
      setAvailableDates(dates);
      // 使用函数式更新获取最新 selectedDate 进行比对
      setSelectedDate(prev => {
        if (dates.length > 0 && !dates.includes(prev)) {
          return dates[0];
        }
        if (dates.length === 0) {
          return '';
        }
        return prev;
      });
      // 切换日志类型时重置过滤和分页
      setColumnFilters({});
      setDraftFilters({});
      setOpenFilterColumn(null);
      setPagination(prev => ({ ...prev, page: 1 }));
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [logType, allDates]);

  // 日期、分页、过滤条件变化时重新加载日志条目
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadEntries();
  }, [loadEntries]);

  // 点击外部关闭筛选下拉面板，滚动或窗口大小变化时也关闭
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (filterPopoverRef.current && !filterPopoverRef.current.contains(event.target as Node)) {
        setOpenFilterColumn(null);
        setFilterPopoverPos(null);
      }
    };
    const handleScrollOrResize = () => {
      setOpenFilterColumn(null);
      setFilterPopoverPos(null);
    };
    if (openFilterColumn !== null) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('scroll', handleScrollOrResize, true);
      window.addEventListener('resize', handleScrollOrResize);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        window.removeEventListener('scroll', handleScrollOrResize, true);
        window.removeEventListener('resize', handleScrollOrResize);
      };
    }
  }, [openFilterColumn]);

  /**
   * 从当前页的条目中提取所有键作为动态列
   * 根据日志类型的预设列顺序排列，追加额外出现的键
   */
  const getDynamicColumns = useCallback((): string[] => {
    if (entries.length === 0) {
      return LOG_TYPE_COLUMNS[logType] || [];
    }
    const keySet = new Set<string>();
    entries.forEach(entry => {
      Object.keys(entry).forEach(key => keySet.add(key));
    });
    const priorityColumns = LOG_TYPE_COLUMNS[logType] || [];
    const orderedColumns: string[] = [];
    // client_audit 的优先列是扁平化命名的（如 client_ip），
    // 它们在原始 JSON 中以嵌套形式存在，不会匹配顶层 keySet 中的键
    // 因此 client_audit 类型需无条件添加所有优先列
    const isClientAudit = logType === 'client_audit';
    // 先按预设顺序添加存在的列
    priorityColumns.forEach(col => {
      if (isClientAudit || keySet.has(col)) {
        orderedColumns.push(col);
        keySet.delete(col);
      }
    });
    // 追加不在预设列表中的其他列
    keySet.forEach(key => orderedColumns.push(key));
    return orderedColumns;
  }, [entries, logType]);

  const columns = getDynamicColumns();

  /**
   * 翻到上一页
   */
  const handlePrevPage = () => {
    if (pagination.page > 1) {
      setPagination(prev => ({ ...prev, page: prev.page - 1 }));
    }
  };

  /**
   * 翻到下一页
   */
  const handleNextPage = () => {
    if (pagination.page < pagination.totalPages) {
      setPagination(prev => ({ ...prev, page: prev.page + 1 }));
    }
  };

  /**
   * 修改页面大小
   * 重置到第一页
   */
  const handlePageSizeChange = (newSize: number) => {
    setPagination(prev => ({ ...prev, page: 1, pageSize: newSize }));
  };

  /**
   * 切换指定列的筛选下拉面板显示状态
   */
  const toggleFilterPopover = (col: string) => {
    const nextOpen = openFilterColumn === col ? null : col;
    setOpenFilterColumn(nextOpen);
    // 打开面板时，初始化草稿为当前已提交的过滤值
    if (nextOpen) {
      setDraftFilters(prev => ({
        ...prev,
        [col]: columnFilters[col] || '',
      }));
      // 计算固定定位坐标
      requestAnimationFrame(() => {
        const cellEl = headerCellRefs.current[col];
        if (cellEl) {
          const rect = cellEl.getBoundingClientRect();
          const popoverWidth = 220;
          // 默认居中于表头单元格
          let left = rect.left + rect.width / 2 - popoverWidth / 2;
          // 如果是第一列，左对齐
          if (columns.indexOf(col) === 0) {
            left = rect.left;
          }
          // 确保不超出视口右边界
          const maxLeft = window.innerWidth - popoverWidth - 8;
          if (left > maxLeft) {
            left = maxLeft;
          }
          if (left < 8) {
            left = 8;
          }
          setFilterPopoverPos({ top: rect.bottom + 4, left });
        }
      });
    } else {
      setFilterPopoverPos(null);
    }
  };

  /**
   * 提交指定列的筛选条件
   */
  const applyColumnFilter = (col: string) => {
    const keyword = draftFilters[col]?.trim() || '';
    if (keyword) {
      setColumnFilters(prev => ({ ...prev, [col]: keyword }));
    } else {
      setColumnFilters(prev => {
        const next = { ...prev };
        delete next[col];
        return next;
      });
    }
    setPagination(prev => ({ ...prev, page: 1 }));
    setOpenFilterColumn(null);
    setFilterPopoverPos(null);
  };

  /**
   * 清除指定列的筛选条件
   */
  const clearColumnFilter = (col: string) => {
    setDraftFilters(prev => ({ ...prev, [col]: '' }));
    setColumnFilters(prev => {
      const next = { ...prev };
      delete next[col];
      return next;
    });
    setPagination(prev => ({ ...prev, page: 1 }));
    setOpenFilterColumn(null);
    setFilterPopoverPos(null);
  };

  /**
   * 渲染内容区域
   */
  const renderContent = () => {
    if (loadingDates) {
      return (
        <div className={styles.spinnerContainer}>
          <Spinner label="Loading date list..." />
        </div>
      );
    }

    if (loading) {
      return (
        <div className={styles.spinnerContainer}>
          <Spinner label="Loading log entries..." />
        </div>
      );
    }

    if (!selectedDate) {
      return (
        <div className={styles.emptyState}>
          <CalendarRegular fontSize={48} />
          <span style={{ fontSize: tokens.fontSizeBase400, fontWeight: tokens.fontWeightSemibold }}>
            Select a date to view logs
          </span>
        </div>
      );
    }

    if (entries.length === 0) {
      return (
        <div className={styles.emptyState}>
          <DocumentSearchRegular fontSize={48} />
          <span style={{ fontSize: tokens.fontSizeBase400, fontWeight: tokens.fontWeightSemibold }}>
            No log entries found
          </span>
          {Object.values(columnFilters).some(v => v?.trim()) && (
            <span style={{ fontSize: tokens.fontSizeBase200, color: tokens.colorNeutralForeground3 }}>
              Try adjusting your filter criteria
            </span>
          )}
        </div>
      );
    }

    return (
      <>
        <div className={styles.tableWrapper}>
          <Table className={styles.table}>
            <TableHeader>
              {/* 列名行：每列显示列名和可点击的下拉箭头 */}
              <TableRow>
                {columns.map(col => (
                  <TableHeaderCell key={col} className={styles.tableHeaderCell}>
                    <div
                      className={styles.headerCellContainer}
                      ref={(el) => { headerCellRefs.current[col] = el; }}
                    >
                      <div
                        className={styles.headerCellContent}
                        onClick={() => toggleFilterPopover(col)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            toggleFilterPopover(col);
                          }
                        }}
                      >
                        <span>{col}</span>
                        <ChevronDownRegular
                          className={mergeClasses(
                            styles.chevronIcon,
                            openFilterColumn === col && styles.chevronIconOpen
                          )}
                        />
                      </div>
                    </div>
                  </TableHeaderCell>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry, index) => (
                <TableRow
                  key={index}
                  className={index % 2 === 0 ? styles.tableRow : styles.tableRowEven}
                >
                  {columns.map(col => {
                    const rawValue = extractValue(entry, col);
                    const displayValue = renderCellValue(rawValue, col);
                    const fullValue = (rawValue === null || rawValue === undefined || rawValue === '-')
                      ? displayValue
                      : String(rawValue);
                    const badge = renderStatusBadge(displayValue, col);
                    let cellMaxWidth = '200px';
                    if (col === 'query_object') {
                      cellMaxWidth = '300px';
                    } else if (col === 'files_returned') {
                      cellMaxWidth = '100px';
                    }
                    return (
                      <TableCell
                        key={col}
                        className={styles.tableCell}
                        style={{ maxWidth: cellMaxWidth }}
                      >
                        <Tooltip content={fullValue} relationship="label">
                          <span>{badge || displayValue}</span>
                        </Tooltip>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {/* 全局固定定位筛选下拉面板，避免被父级 overflow 裁剪 */}
        {openFilterColumn && filterPopoverPos && (
          <div
            className={styles.filterPopoverFixed}
            ref={filterPopoverRef}
            style={{ top: filterPopoverPos.top, left: filterPopoverPos.left }}
          >
            <div className={styles.filterPopoverHeader}>
              Filter by {openFilterColumn}
            </div>
            <div className={styles.filterPopoverInputOverrides}>
              <Input
                size="small"
                value={draftFilters[openFilterColumn] || ''}
                onChange={(_, data) => {
                  setDraftFilters(prev => ({ ...prev, [openFilterColumn]: data.value }));
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    applyColumnFilter(openFilterColumn);
                  }
                  if (e.key === 'Escape') {
                    setOpenFilterColumn(null);
                    setFilterPopoverPos(null);
                  }
                }}
                placeholder={`Filter ${openFilterColumn}...`}
                contentBefore={<SearchRegular fontSize={14} />}
                className={styles.filterPopoverInput}
                autoFocus
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
              <Button
                size="small"
                appearance="subtle"
                onClick={() => clearColumnFilter(openFilterColumn)}
              >
                Clear
              </Button>
              <Button
                size="small"
                appearance="primary"
                onClick={() => applyColumnFilter(openFilterColumn)}
              >
                Apply
              </Button>
            </div>
          </div>
        )}
      </>
    );
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        {/* 卡片头部 */}
        <div className={styles.cardHeader}>
          <div style={{ display: 'flex', alignItems: 'baseline' }}>
            <span className={styles.title}>Audit Log Viewer</span>
            {!loading && !loadingDates && entries.length > 0 && (
              <span className={styles.entryCount}>
                {pagination.total.toLocaleString()} entries
              </span>
            )}
          </div>
          {/* 活跃过滤条件标签 */}
          {Object.keys(columnFilters).filter(col => columnFilters[col]?.trim()).length > 0 && (
            <div className={styles.activeFilterTag}>
              <FilterRegular fontSize={12} />
              <span>{Object.entries(columnFilters)
                .filter(([, v]) => v?.trim())
                .map(([col, val]) => `${col}: "${val}"`)
                .join(', ')}</span>
              <Button
                appearance="transparent"
                size="small"
                icon={<DismissRegular fontSize={12} />}
                onClick={() => {
                  setColumnFilters({});
                  setDraftFilters({});
                  setPagination(prev => ({ ...prev, page: 1 }));
                }}
                style={{ minWidth: 'auto', padding: '2px' }}
              />
            </div>
          )}
        </div>

        {/* 错误提示 */}
        {error && (
          <MessageBar intent="error" className={styles.errorBar}>
            <MessageBarBody style={{ display: 'flex', alignItems: 'center' }}>
              <span>{error}</span>
              <Button
                appearance="transparent"
                size="small"
                onClick={() => {
                  setError(null);
                  if (!selectedDate) {
                    loadDateList();
                  } else {
                    loadEntries();
                  }
                }}
                style={{ marginLeft: tokens.spacingHorizontalM }}
              >
                Retry
              </Button>
            </MessageBarBody>
          </MessageBar>
        )}

        {/* 工具栏：左右分区 */}
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            {/* 日志类型选择 */}
            <div className={styles.toolbarItem}>
              <span className={styles.toolbarLabel}>Log Type</span>
              <Dropdown
                value={LOG_TYPE_LABELS[logType]}
                onOptionSelect={(_, data) => {
                  const newType = data.optionValue as 'admin_audit' | 'client_audit' | 'app';
                  if (newType && newType !== logType) {
                    setLogType(newType);
                  }
                }}
                style={{ minWidth: '160px' }}
              >
                {Object.entries(LOG_TYPE_LABELS).map(([value, label]) => (
                  <Option key={value} value={value}>
                    {label}
                  </Option>
                ))}
              </Dropdown>
            </div>

            {/* 日期选择 */}
            <div className={styles.toolbarItem}>
              <span className={styles.toolbarLabel}>Date</span>
              <Dropdown
                value={selectedDate || 'Select date'}
                onOptionSelect={(_, data) => {
                  setSelectedDate(data.optionValue || '');
                  setPagination(prev => ({ ...prev, page: 1 }));
                }}
                style={{ minWidth: '140px' }}
                placeholder="Select date"
              >
                {availableDates.map(date => (
                  <Option key={date} value={date}>
                    {date}
                  </Option>
                ))}
              </Dropdown>
            </div>
          </div>
        </div>

        {/* 内容区域 */}
        {renderContent()}

        {/* 分页控件 */}
        {!loading && !loadingDates && selectedDate && entries.length > 0 && (
          <div className={styles.pagination}>
            <Button
              icon={<ChevronLeftRegular className={styles.paginationIcon} />}
              onClick={handlePrevPage}
              disabled={pagination.page <= 1}
              className={styles.paginationButton}
            >
              Previous
            </Button>
            <span className={styles.pageIndicator}>
              Page {pagination.page} of {pagination.totalPages}
            </span>
            <Button
              onClick={handleNextPage}
              disabled={pagination.page >= pagination.totalPages}
              className={styles.paginationButton}
            >
              <span className={styles.paginationContent}>
                Next
                <ChevronRightRegular className={styles.paginationIcon} />
              </span>
            </Button>

            {/* 页面大小选择器 */}
            <span className={styles.infoText} style={{ marginLeft: tokens.spacingHorizontalL }}>
              Page Size:
            </span>
            <Dropdown
              className={styles.pageSizeSelector}
              value={String(pagination.pageSize)}
              onOptionSelect={(_, data) => {
                const newSize = parseInt(data.optionValue || '50', 10);
                if (!isNaN(newSize)) {
                  handlePageSizeChange(newSize);
                }
              }}
            >
              {PAGE_SIZE_OPTIONS.map(size => (
                <Option key={size} value={String(size)} text={String(size)}>
                  {size}
                </Option>
              ))}
            </Dropdown>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuditLogViewer;

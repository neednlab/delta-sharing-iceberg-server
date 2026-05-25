/* eslint-disable react-refresh/only-export-components */
import { type ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { FluentProvider, webLightTheme } from '@fluentui/react-components'
import { render, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

/**
 * Providers 包装器组件
 * 为测试组件提供必要的上下文：
 * - FluentProvider: Fluent UI v9 组件库主题
 * - MemoryRouter: 路由上下文（jsdom 无浏览器 URL bar）
 */
function AllTheProviders({
  children,
  initialRoute = '/',
}: {
  children: React.ReactNode
  initialRoute?: string
}) {
  return (
    <FluentProvider theme={webLightTheme}>
      <MemoryRouter initialEntries={[initialRoute]}>
        {children}
      </MemoryRouter>
    </FluentProvider>
  )
}

/**
 * 自定义渲染选项，扩展 RTL 的 RenderOptions
 */
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  initialRoute?: string
}

/**
 * 带 Providers 的自定义 render 函数
 * 自动包裹 FluentProvider + MemoryRouter，无需在每个测试中手动设置
 *
 * @param ui - 要渲染的 React 元素
 * @param options - 可选配置，支持 initialRoute 设置初始路由
 * @returns RTL render 结果 + userEvent 实例
 */
function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions = {}
) {
  const { initialRoute, ...renderOptions } = options

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <AllTheProviders initialRoute={initialRoute}>
        {children}
      </AllTheProviders>
    )
  }

  return {
    user: userEvent.setup(),
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  }
}

export { renderWithProviders }

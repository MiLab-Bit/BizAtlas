import { Component, type ErrorInfo, type ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./card";

/**
 * 全局错误边界。
 *
 * 背景：此前整个项目没有任何 ErrorBoundary / componentDidCatch，
 * 任意一个组件在渲染期抛错（例如后端契约漂移导致 `对象.toFixed()`）都会让
 * 整棵 React 树卸载 —— 表现为「点进某个页面 → 全白，连左侧导航都没了」。
 *
 * 挂在两处：
 *   1. App 根层（兜底，防整站白屏）
 *   2. Shell 的 <Outlet /> 外层（页面级，出错时保留导航与侧边栏，可切页自救）
 */
interface Props {
  children: ReactNode;
  /** 出错区块名称，用于错误卡片标题与日志 */
  label?: string;
  /** key 变化时自动重置错误态（用于路由切换后恢复） */
  resetKey?: string;
}

interface State {
  error: Error | null;
  stack: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, stack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const stack = info.componentStack ?? "";
    // 打到控制台便于 F12 定位；如需远端上报，这里是唯一接入点
    console.error(
      `[BizAtlas][ErrorBoundary]${this.props.label ? ` ${this.props.label}` : ""} 渲染失败：`,
      error,
      stack,
    );
    this.setState({ stack });
  }

  componentDidUpdate(prev: Props) {
    // 路由切换后自动复位，避免一次崩溃污染整个会话
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null, stack: null });
    }
  }

  private handleReset = () => this.setState({ error: null, stack: null });

  render() {
    const { error, stack } = this.state;
    if (!error) return this.props.children;

    return (
      <Card className="m-5 border-destructive/30">
        <CardHeader>
          <CardTitle className="text-base text-destructive">
            {this.props.label ? `「${this.props.label}」` : "此模块"}渲染出错
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            页面其余部分不受影响。错误已被隔离，你可以返回其他页面继续操作，或重试当前模块。
          </p>
          <pre className="max-h-40 overflow-auto rounded border border-border bg-secondary/50 p-3 text-xs text-foreground">
            {error.name}: {error.message}
          </pre>
          {stack && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">展开调用栈</summary>
              <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap">{stack}</pre>
            </details>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={this.handleReset}
              className="rounded-md border border-border bg-secondary px-3 py-1.5 text-sm font-medium text-foreground hover:bg-secondary/80"
            >
              重试
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary/60"
            >
              刷新页面
            </button>
          </div>
        </CardContent>
      </Card>
    );
  }
}

/** 页面级包装：Shell 内每个路由内容外层套一层，崩溃时导航仍可用。 */
export function PageErrorBoundary({
  children,
  label,
  resetKey,
}: {
  children: ReactNode;
  label?: string;
  resetKey?: string;
}) {
  return (
    <ErrorBoundary label={label} resetKey={resetKey}>
      {children}
    </ErrorBoundary>
  );
}

/**
 * 微信云开发 + CloudBase AnyService 封装。
 * 仅在 prod 构建生效; dev 走 Taro.request 直连 localhost (见 request.ts)。
 *
 * 文档: https://developers.weixin.qq.com/miniprogram/dev/wxcloud/guide/wxcloud-callContainer.html
 */

interface CallContainerResponse {
  data: string | Record<string, unknown>;
  statusCode: number;
  header: Record<string, string>;
}

interface WXCloud {
  init(opts: { env: string; traceUser?: boolean }): void;
  DYNAMIC_CURRENT_ENV: string;
  callContainer(opts: {
    config?: { env: string };
    path: string;
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    data?: string | Record<string, unknown>;
    header?: Record<string, string>;
    dataType?: string;
    responseType?: string;
  }): Promise<CallContainerResponse>;
}

interface WXWithCloud {
  cloud: WXCloud;
}

// AnyService 固定 header: X-WX-SERVICE 标识接入类型为 tcbanyservice
const ANY_SERVICE_HEADER = { 'X-WX-SERVICE': 'tcbanyservice' };

function getWXCloud(): WXCloud {
  const w = wx as unknown as WXWithCloud;
  if (!w.cloud) {
    throw new Error('wx.cloud is not initialized. Call initCloud() in app onLaunch first.');
  }
  return w.cloud;
}

/** 应用启动时调用一次 (在 app.tsx componentDidMount 里) */
export function initCloud(): void {
  if (!CLOUD_ENV) {
    // dev 构建: 不初始化, 走 Taro.request
    return;
  }
  const w = wx as unknown as WXWithCloud;
  if (w.cloud) {
    w.cloud.init({ env: CLOUD_ENV, traceUser: true });
  }
}

/**
 * 通过 AnyService 调用后端容器。
 * path 形如 '/api/chainkb/tree' (含 /api 前缀, 含 querystring)。
 */
export async function callContainer<T>(
  path: string,
  opts: {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    data?: unknown;
    header?: Record<string, string>;
  } = {},
): Promise<T> {
  const { method = 'GET', data, header } = opts;
  const cloud = getWXCloud();

  const res = await cloud.callContainer({
    path,
    method,
    data: data as string | Record<string, unknown> | undefined,
    header: {
      ...ANY_SERVICE_HEADER,
      'X-AnyService-Name': ANY_SERVICE_NAME,
      'Content-Type': 'application/json',
      ...header,
    },
  });

  if (res.statusCode < 200 || res.statusCode >= 300) {
    const body = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
    let detail = '';
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail || '';
    } catch {
      detail = body.slice(0, 200);
    }
    throw new Error(detail || `HTTP ${res.statusCode}`);
  }
  return res.data as T;
}

/** prod 为 true, dev 为 false; request.ts 据此分发 */
export const IS_CLOUD_ENABLED = !!CLOUD_ENV;

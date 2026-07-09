import Taro from '@tarojs/taro';
import { callContainer, IS_CLOUD_ENABLED } from './cloud';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  header?: Record<string, string>;
}

export class ApiError extends Error {
  statusCode: number;
  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
    this.name = 'ApiError';
  }
}

/**
 * 统一请求封装。
 * - dev (npm run dev:weapp): Taro.request → localhost:8000
 * - prod (npm run build:weapp): wx.cloud.callContainer → CloudBase AnyService → Lighthouse
 *
 * path 形如 '/api/chainkb/tree' (含 /api 前缀)。
 * 非 2xx 状态码抛 ApiError。网络错误抛 Error。
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const fullPath = path + buildQuery(opts.query);

  if (IS_CLOUD_ENABLED) {
    try {
      return await callContainer<T>(fullPath, {
        method: opts.method,
        data: opts.body,
        header: opts.header,
      });
    } catch (e) {
      // callContainer 抛的是普通 Error, 这里统一包成 ApiError 保持调用方语义
      throw new ApiError(0, e instanceof Error ? e.message : String(e));
    }
  }

  // dev 直连
  const res = await Taro.request({
    url: BASE_URL_ENV + fullPath,
    method: opts.method || 'GET',
    data: opts.body,
    header: { 'Content-Type': 'application/json', ...opts.header },
    timeout: 15000,
  });

  if (res.statusCode < 200 || res.statusCode >= 300) {
    const msg = (res.data && (res.data as { detail?: string }).detail) || `HTTP ${res.statusCode}`;
    throw new ApiError(res.statusCode, msg);
  }
  return res.data as T;
}

function buildQuery(query?: RequestOptions['query']): string {
  if (!query) return '';
  const entries = Object.entries(query).filter(([, v]) => v !== undefined && v !== '');
  if (entries.length === 0) return '';
  const params = entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return '?' + params.join('&');
}

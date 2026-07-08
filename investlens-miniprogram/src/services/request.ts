import Taro from '@tarojs/taro';

// dev: localhost (微信开发者工具需勾"不校验合法域名")
// prod: 通过 config/prod.js defineConstants 注入 BASE_URL
const BASE_URL = typeof BASE_URL_ENV !== 'undefined'
  ? BASE_URL_ENV
  : 'http://localhost:8000';

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
 * 统一 Taro.request 封装。
 * path 形如 '/api/chainkb/tree' (含 /api 前缀)。
 * 非 2xx 状态码抛 ApiError。网络错误抛 Error。
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, header } = opts;
  const url = BASE_URL + path + buildQuery(query);

  const res = await Taro.request({
    url,
    method,
    data: body,
    header: { 'Content-Type': 'application/json', ...header },
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

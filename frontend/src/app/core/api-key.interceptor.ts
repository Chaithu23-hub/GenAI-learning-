import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../environments/environment';

export const apiKeyInterceptor: HttpInterceptorFn = (req, next) => {
  const key = environment.apiKey;
  if (!key) return next(req);

  const targetsBackend = isBackendRequest(req.url, environment.apiUrl);

  if (!targetsBackend) return next(req);
  return next(req.clone({ setHeaders: { 'X-API-Key': key } }));
};

function isBackendRequest(requestUrl: string, configuredApiUrl: string): boolean {
  try {
    const configuredBase = configuredApiUrl.trim();
    if (!configuredBase) return false;
    const origin = globalThis.location.origin;
    const api = new URL(configuredBase, origin);
    const request = new URL(requestUrl, origin);
    if (api.origin !== request.origin) return false;

    const basePath = api.pathname.replace(/\/+$/, '');
    return !basePath || request.pathname === basePath || request.pathname.startsWith(`${basePath}/`);
  } catch {
    return false;
  }
}

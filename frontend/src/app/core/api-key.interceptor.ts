import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../environments/environment';

// Attach the configured API key to backend calls only. An empty apiUrl would
// make `startsWith('')` true for every URL, so we treat empty as "same origin"
// and require the request path to start with '/api/' instead.
export const apiKeyInterceptor: HttpInterceptorFn = (req, next) => {
  const key = environment.apiKey;
  if (!key) return next(req);

  const base = environment.apiUrl?.trim();
  const targetsBackend = base
    ? req.url.startsWith(base)
    : req.url.startsWith('/api/') || req.url.startsWith('api/');

  if (!targetsBackend) return next(req);
  return next(req.clone({ setHeaders: { 'X-API-Key': key } }));
};

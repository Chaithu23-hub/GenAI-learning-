import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { ProblemDetails } from '../models/types';

// Normalise backend RFC 7807 problem+json errors into a friendly message
// while preserving the original response for debugging.
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
    public problem?: ProblemDetails,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse) {
        const problem = err.error as ProblemDetails | null | undefined;
        const message =
          problem?.detail ||
          problem?.title ||
          err.message ||
          'Unexpected network error';
        return throwError(
          () => new ApiError(err.status, message, problem?.request_id, problem ?? undefined),
        );
      }
      return throwError(() => err);
    }),
  );
};

import { HttpRequest } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { apiKeyInterceptor } from './api-key.interceptor';

describe('apiKeyInterceptor', () => {
  const originalApiUrl = environment.apiUrl;
  const originalApiKey = environment.apiKey;
  const forwardedHeaders: string[] = [];

  function run(url: string): string | null {
    const request = new HttpRequest('GET', url);
    apiKeyInterceptor(request, (forwarded) => {
      forwardedHeaders.push(forwarded.headers.get('X-API-Key') ?? '');
      return null as never;
    });
    return forwardedHeaders.pop() || null;
  }

  beforeEach(() => {
    environment.apiKey = 'dummy-test-key';
    environment.apiUrl = 'https://api.example.test/api';
  });

  afterEach(() => {
    environment.apiUrl = originalApiUrl;
    environment.apiKey = originalApiKey;
    forwardedHeaders.length = 0;
  });

  it('adds the key to the configured absolute API URL including query strings', () => {
    expect(run('https://api.example.test/api/ask?query=notice')).toBe('dummy-test-key');
  });

  it('adds the key to relative API requests when the configured URL is relative', () => {
    environment.apiUrl = '/api';
    expect(run('/api/ask?query=notice')).toBe('dummy-test-key');
  });

  it('does not add the key to a foreign origin with a matching URL prefix', () => {
    environment.apiUrl = 'https://api.example.test';
    expect(run('https://api.example.test.attacker.test/api/ask')).toBeNull();
  });

  it('requires a path segment boundary after the configured API path', () => {
    expect(run('https://api.example.test/apievil/ask')).toBeNull();
  });

  it('does not add the key to protocol-relative foreign URLs', () => {
    environment.apiUrl = '/api';
    expect(run('//attacker.test/api/ask')).toBeNull();
  });

  it('fails closed when the configured API URL is invalid', () => {
    environment.apiUrl = 'https://[invalid';
    expect(run('https://api.example.test/api/ask')).toBeNull();
  });

  it('fails closed when the configured API URL is empty', () => {
    environment.apiUrl = '  ';
    expect(run('/api/ask')).toBeNull();
  });
});

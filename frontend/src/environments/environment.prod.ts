export const environment = {
  production: true,
  apiUrl: (globalThis as any)['LEGAL_RAG_API_URL'] || '/api',
  apiKey: (globalThis as any)['LEGAL_RAG_API_KEY'] || '',
};

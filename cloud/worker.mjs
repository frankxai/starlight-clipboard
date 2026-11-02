import {PUBLIC_ASSETS} from './assets.mjs';
import {authorize, accessConfigured, AccessError} from './access.mjs';
import {boundedJson, selection, classify, InputError} from './classify.mjs';

export const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'";
const HEADERS = Object.freeze({
  'Cache-Control': 'no-store', 'Content-Security-Policy': CSP,
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security': 'max-age=31536000',
});
function json(body, status = 200) {
  return Response.json(body, {status, headers: HEADERS});
}
function inferenceReady(env) {
  return env.INFERENCE_ENABLED === 'true' && typeof env.INFERENCE_APPROVAL_ID === 'string' &&
    !!env.INFERENCE_APPROVAL_ID.trim() && typeof env.AI?.run === 'function' &&
    typeof env.INFERENCE_RATE_LIMIT?.limit === 'function' && accessConfigured(env);
}

export function createWorker(assets = PUBLIC_ASSETS, fetcher = fetch) {
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      const id = crypto.randomUUID();
      try {
        if (url.protocol !== 'https:') return json({error: 'https_required'}, 400);
        // There is no body handling or pass-through for incoming shares at the host.
        // An installed service worker must commit them on the phone instead.
        if (request.method === 'POST' && url.pathname === '/share') {
          return json({error: 'local_share_handler_required', hint: 'Open Starlight first, or return to the source and paste explicitly.'}, 428);
        }
        if ((request.method === 'GET' || request.method === 'HEAD') && url.pathname === '/api/health') {
          const response = json({schema: 'starlight.clipboard-cloud-health.v1', app_id: 'clipboard',
            release: env.RELEASE_ID || 'unpackaged', archive_storage: 'device-local-plaintext-web-beta',
            account_sync: 'not-implemented', automatic_uploads: false,
            assets_packaged: Object.hasOwn(assets, '/index.html'),
            inference_enabled: inferenceReady(env), access_configured: accessConfigured(env),
            review_state: 'private-beta-candidate'});
          return request.method === 'HEAD' ? new Response(null, response) : response;
        }
        if (url.pathname === '/api/classify') {
          if (request.method !== 'POST') return json({error: 'method_not_allowed'}, 405);
          if (!inferenceReady(env)) {
            return json({error: 'inference_not_activated'}, 503);
          }
          const identity = await authorize(request, env, fetcher);
          if (!/^https:\/\/[^/]+$/.test(env.APP_ORIGIN || '') || url.origin !== env.APP_ORIGIN ||
              request.headers.get('Origin') !== env.APP_ORIGIN ||
              !['same-origin', null].includes(request.headers.get('Sec-Fetch-Site'))) {
            return json({error: 'origin_refused'}, 403);
          }
          const rate = await env.INFERENCE_RATE_LIMIT.limit({key: identity.subject});
          if (!rate.success) return json({error: 'rate_limited'}, 429);
          const text = selection(await boundedJson(request));
          const result = await classify(text, env);
          return json({schema: 'starlight.clipboard-suggestion.v1', request_id: id, ...result});
        }
        if (!['GET', 'HEAD'].includes(request.method)) return json({error: 'method_not_allowed'}, 405);
        if (url.pathname.startsWith('/api/')) return json({error: 'not_found'}, 404);
        const path = url.pathname === '/' ? '/index.html' : url.pathname;
        if (!Object.hasOwn(assets, path)) return json({error: 'not_found'}, 404);
        await authorize(request, env, fetcher);
        const asset = assets[path];
        const bytes = request.method === 'HEAD' ? null : Uint8Array.from(atob(asset.base64), c => c.charCodeAt(0));
        return new Response(bytes, {headers: {...HEADERS, 'Content-Type': asset.type,
          ...(path === '/sw.js' ? {'Service-Worker-Allowed': '/'} : {})}});
      } catch (error) {
        if (error instanceof AccessError || error instanceof InputError) return json({error: error.code}, error.status);
        // No raw exception, request URL, clipboard content or identity is logged/returned.
        return json({error: 'request_failed', request_id: id}, 502);
      }
    },
  };
}

export default createWorker();

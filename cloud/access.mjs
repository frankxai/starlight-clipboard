import {createRemoteJWKSet, customFetch, jwtVerify} from 'jose';

export class AccessError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

export function accessConfigured(env) {
  return /^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(env.ACCESS_TEAM_DOMAIN || '') &&
    /^[a-f0-9]{64}$/.test(env.ACCESS_AUD || '');
}

export async function authorize(request, env, fetcher = fetch) {
  const issuer = env.ACCESS_TEAM_DOMAIN;
  const audience = env.ACCESS_AUD;
  if (!accessConfigured(env)) {
    throw new AccessError(503, 'access_not_configured');
  }
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token || token.length > 8192) throw new AccessError(401, 'access_required');
  try {
    // The configured issuer is the only network destination; JWT jku/x5u are ignored.
    const keys = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`), {
      timeoutDuration: 3000,
      [customFetch]: fetcher,
    });
    const {payload} = await jwtVerify(token, keys, {
      issuer, audience, algorithms: ['RS256'], clockTolerance: 5,
      requiredClaims: ['iss', 'aud', 'sub', 'iat', 'exp'], maxTokenAge: '24h',
    });
    if (payload.type !== 'app' || typeof payload.sub !== 'string' ||
        !payload.sub || payload.sub.length > 256) throw new Error('Unsupported identity');
    return {subject: payload.sub};
  } catch {
    // Never echo JWTs, claims, upstream errors or key material.
    throw new AccessError(401, 'access_invalid');
  }
}

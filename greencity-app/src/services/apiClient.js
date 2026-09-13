const configuredBaseUrl = import.meta.env?.VITE_API_BASE_URL;
const DEFAULT_BASE_URL = configuredBaseUrl || '/api/v1';

const trimTrailingSlash = value => String(value || '').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'ERR-UNKNOWN', correlationId = '', cause } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

async function readPayload(response) {
  const contentType = response.headers?.get?.('content-type') || '';
  if (!contentType.includes('application/json')) return null;
  try { return await response.json(); } catch { return null; }
}

function errorFromResponse(response, payload, fallbackCorrelationId) {
  const detail = payload?.error;
  return new ApiError(detail?.message || 'Máy chủ không thể xử lý yêu cầu.', {
    status: response.status,
    code: detail?.code || `ERR-HTTP-${response.status}`,
    correlationId: detail?.correlation_id || response.headers?.get?.('X-Correlation-ID') || fallbackCorrelationId,
  });
}

function assertUserInfo(user, correlationId = '') {
  const validSites = Array.isArray(user?.allowed_sites) && user.allowed_sites.every(site => (
    site && typeof site === 'object' && typeof site.id === 'string'
    && typeof site.code === 'string' && typeof site.name === 'string'
  ));
  const validActiveSite = user?.active_site_id === null
    || (typeof user?.active_site_id === 'string' && user.allowed_sites?.some(site => site.id === user.active_site_id));
  if (!user || typeof user !== 'object' || typeof user.account_id !== 'string'
    || typeof user.full_name !== 'string' || !Array.isArray(user.roles)
    || !validSites || !validActiveSite) {
    throw new ApiError('Phản hồi hồ sơ đăng nhập không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return user;
}

function assertServiceRequestList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items) || !Number.isInteger(payload.page)
    || !Number.isInteger(payload.page_size) || !Number.isInteger(payload.total)) {
    throw new ApiError('Phản hồi danh sách yêu cầu không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertUnit360(payload, correlationId = '') {
  const requiredStrings = ['id', 'unit_number', 'building_id', 'building_code', 'building_name', 'site_id', 'site_code', 'site_name'];
  const validResidents = Array.isArray(payload?.residents) && payload.residents.every(resident => (
    resident && typeof resident === 'object'
    && typeof resident.person_id === 'string'
    && typeof resident.full_name === 'string'
    && typeof resident.phone_masked === 'string'
    && typeof resident.email_masked === 'string'
    && typeof resident.relationship_type === 'string'
    && typeof resident.is_active === 'boolean'
    && (resident.ownership_ratio === null || typeof resident.ownership_ratio === 'string')
    && typeof resident.valid_from === 'string'
    && (resident.valid_to === null || typeof resident.valid_to === 'string')
  ));
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')
    || !Number.isInteger(payload.floor) || !Number.isInteger(payload.version)
    || typeof payload.residents_visible !== 'boolean' || !validResidents) {
    throw new ApiError('Phản hồi căn hộ 360° không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

export function createApiClient({
  baseUrl = DEFAULT_BASE_URL,
  fetchImpl = globalThis.fetch,
  onUnauthorized = () => {},
  correlationIdFactory = () => globalThis.crypto?.randomUUID?.(),
} = {}) {
  if (typeof fetchImpl !== 'function') throw new TypeError('fetchImpl must be a function');
  const apiBaseUrl = trimTrailingSlash(baseUrl);
  let accessToken = '';
  let sessionRevision = 0;

  const advanceSession = token => {
    accessToken = token;
    sessionRevision += 1;
  };
  const clearSession = () => advanceSession('');
  const staleSessionError = () => {
    const error = new Error('The authenticated request belongs to an inactive session scope.');
    error.name = 'AbortError';
    return error;
  };

  async function request(path, { method = 'GET', body, signal, authenticated = true } = {}) {
    const requestCorrelationId = correlationIdFactory?.() || '';
    const requestRevision = sessionRevision;
    const requestToken = accessToken;
    const headers = { Accept: 'application/json' };
    if (requestCorrelationId) headers['X-Correlation-ID'] = requestCorrelationId;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (authenticated && requestToken) headers.Authorization = `Bearer ${requestToken}`;

    let response;
    try {
      response = await fetchImpl(`${apiBaseUrl}${path}`, {
        method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      if (authenticated && requestRevision !== sessionRevision) throw staleSessionError();
      if (cause?.name === 'AbortError') throw cause;
      throw new ApiError('Không thể kết nối máy chủ. Kiểm tra mạng rồi thử lại.', {
        code: 'ERR-NETWORK', correlationId: requestCorrelationId, cause,
      });
    }

    if (authenticated && requestRevision !== sessionRevision) throw staleSessionError();
    const payload = await readPayload(response);
    if (authenticated && requestRevision !== sessionRevision) throw staleSessionError();
    const responseCorrelationId = response.headers?.get?.('X-Correlation-ID') || requestCorrelationId;
    if (!response.ok) {
      const error = errorFromResponse(response, payload, responseCorrelationId);
      if (response.status === 401) {
        const isCurrentSession = requestRevision === sessionRevision && requestToken === accessToken;
        if (isCurrentSession && requestToken) {
          clearSession();
          onUnauthorized(error);
        }
      }
      throw error;
    }
    return { payload, correlationId: responseCorrelationId };
  }

  return {
    async authenticate(username, password, { signal } = {}) {
      clearSession();
      const login = await request('/auth/login', {
        method: 'POST', body: { username, password }, signal, authenticated: false,
      });
      const issuedToken = login.payload?.access_token;
      if (typeof issuedToken !== 'string' || !issuedToken) {
        throw new ApiError('Phản hồi đăng nhập không có phiên hợp lệ.', {
          code: 'ERR-INVALID-RESPONSE', correlationId: login.correlationId,
        });
      }
      advanceSession(issuedToken);
      try {
        const me = await request('/auth/me', { signal });
        return assertUserInfo(me.payload, me.correlationId);
      } catch (error) {
        clearSession();
        throw error;
      }
    },

    async switchSite(siteId, { signal } = {}) {
      // Invalidate every request started in the old site before switching.
      sessionRevision += 1;
      const switched = await request('/auth/switch-site', {
        method: 'POST', body: { site_id: siteId }, signal,
      });
      const issuedToken = switched.payload?.access_token;
      if (typeof issuedToken !== 'string' || !issuedToken) {
        throw new ApiError('Phản hồi đổi site không có phiên hợp lệ.', {
          code: 'ERR-INVALID-RESPONSE', correlationId: switched.correlationId,
        });
      }
      advanceSession(issuedToken);
      try {
        const me = await request('/auth/me', { signal });
        return assertUserInfo(me.payload, me.correlationId);
      } catch (error) {
        clearSession();
        throw error;
      }
    },

    async listServiceRequests({ status, page = 1, page_size = 20, signal } = {}) {
      const query = new URLSearchParams();
      if (status) query.set('status', status);
      query.set('page', String(page));
      query.set('page_size', String(page_size));
      const result = await request(`/service-requests?${query}`, { signal });
      return assertServiceRequestList(result.payload, result.correlationId);
    },

    async getUnit360(unitId, { signal } = {}) {
      const result = await request(`/units/${encodeURIComponent(unitId)}/360`, { signal });
      return assertUnit360(result.payload, result.correlationId);
    },

    clearSession,
    hasSession: () => Boolean(accessToken),
  };
}

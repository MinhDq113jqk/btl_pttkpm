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

function assertServiceRequestFormOptions(payload, correlationId = '') {
  const isBuilding = item => item && typeof item.id === 'string'
    && typeof item.code === 'string' && typeof item.name === 'string';
  const isCategory = item => isBuilding(item)
    && (item.building_id === null || typeof item.building_id === 'string');
  const isUnit = item => item && typeof item.id === 'string'
    && typeof item.unit_number === 'string' && typeof item.building_id === 'string';
  if (!payload || !Array.isArray(payload.buildings) || !Array.isArray(payload.categories)
    || !Array.isArray(payload.units) || !payload.buildings.every(isBuilding)
    || !payload.categories.every(isCategory) || !payload.units.every(isUnit)) {
    throw new ApiError('Phản hồi lựa chọn tạo yêu cầu không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertCreatedServiceRequest(payload, correlationId = '') {
  const requiredStrings = ['id', 'code', 'title', 'priority', 'status'];
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')) {
    throw new ApiError('Phản hồi tạo yêu cầu không đúng định dạng.', {
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

function assertCleaningChecklist(item, correlationId = '') {
  const results = new Set(['PENDING', 'PASS', 'FAIL', 'NOT_APPLICABLE']);
  if (!item || typeof item.id !== 'string' || !Number.isInteger(item.position)
    || typeof item.label !== 'string' || typeof item.is_required !== 'boolean'
    || !results.has(item.result) || !Number.isInteger(item.version)) {
    throw new ApiError('Phản hồi checklist vệ sinh không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return item;
}

function assertCleaningTask(payload, correlationId = '') {
  const statuses = new Set(['PLANNED', 'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'ACCEPTED', 'MISSED', 'REWORK_REQUIRED', 'CANCELLED']);
  const requiredStrings = ['id', 'shift_id', 'route_id', 'route_code', 'route_name', 'area_id', 'area_code', 'area_name', 'tenant_id', 'site_id', 'building_id', 'status', 'scheduled_start_at', 'scheduled_end_at'];
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')
    || !statuses.has(payload.status) || !Number.isInteger(payload.version)
    || !Array.isArray(payload.checklist)) {
    throw new ApiError('Phản hồi task vệ sinh không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.checklist.forEach(item => assertCleaningChecklist(item, correlationId));
  return payload;
}

function assertCleaningTaskList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách task vệ sinh không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertCleaningTask(item, correlationId));
  return payload;
}

function assertCleaningRoutes(payload, correlationId = '') {
  if (!Array.isArray(payload) || !payload.every(item => item && typeof item.id === 'string'
    && typeof item.code === 'string' && typeof item.name === 'string' && typeof item.building_id === 'string')) {
    throw new ApiError('Phản hồi tuyến vệ sinh không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertCleaningAssignees(payload, correlationId = '') {
  if (!Array.isArray(payload) || !payload.every(item => item && typeof item.id === 'string' && typeof item.full_name === 'string')) {
    throw new ApiError('Phản hồi nhân viên vệ sinh không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertSecurityPatrolWindow(item, correlationId = '') {
  const statuses = new Set(['SCHEDULED', 'COMPLETED', 'MISSED', 'CANCELLED']);
  const requiredStrings = ['id', 'security_shift_id', 'patrol_point_id', 'patrol_point_code', 'patrol_point_name', 'building_id', 'window_start_at', 'window_end_at', 'status'];
  if (!item || requiredStrings.some(field => typeof item[field] !== 'string')
    || !statuses.has(item.status) || !Number.isInteger(item.version) || !Array.isArray(item.logs)) {
    throw new ApiError('Phản hồi cửa sổ tuần tra không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  item.logs.forEach(log => {
    if (!log || typeof log.id !== 'string' || typeof log.event_type !== 'string' || typeof log.occurred_at !== 'string') {
      throw new ApiError('Phản hồi nhật ký tuần tra không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
    }
  });
  return item;
}

function assertSecurityShift(payload, correlationId = '') {
  const statuses = new Set(['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']);
  const requiredStrings = ['id', 'tenant_id', 'site_id', 'building_id', 'scheduled_start_at', 'scheduled_end_at', 'status'];
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')
    || !statuses.has(payload.status) || !Number.isInteger(payload.version)
    || !Array.isArray(payload.handoffs) || !Array.isArray(payload.visitors) || !Array.isArray(payload.patrol_windows)) {
    throw new ApiError('Phản hồi ca trực an ninh không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.patrol_windows.forEach(item => assertSecurityPatrolWindow(item, correlationId));
  return payload;
}

function assertSecurityIncident(payload, correlationId = '') {
  const statuses = new Set(['NEW', 'TRIAGED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED']);
  const severities = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);
  const requiredStrings = ['id', 'building_id', 'code', 'incident_type', 'severity', 'status', 'title', 'description', 'occurred_at', 'reported_by_id'];
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')
    || !statuses.has(payload.status) || !severities.has(payload.severity)
    || !Number.isInteger(payload.version) || !Array.isArray(payload.escalations) || !Array.isArray(payload.evidence)) {
    throw new ApiError('Phản hồi sự cố an ninh không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertSecurityDashboard(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.shifts) || !Array.isArray(payload.exceptions) || !Array.isArray(payload.incidents)) {
    throw new ApiError('Phản hồi dashboard an ninh không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.shifts.forEach(item => assertSecurityShift(item, correlationId));
  payload.exceptions.forEach(item => assertSecurityPatrolWindow(item, correlationId));
  payload.incidents.forEach(item => assertSecurityIncident(item, correlationId));
  return payload;
}

function assertSecurityPoints(payload, correlationId = '') {
  if (!Array.isArray(payload) || !payload.every(item => item && typeof item.id === 'string'
    && typeof item.code === 'string' && typeof item.name === 'string' && typeof item.building_id === 'string')) {
    throw new ApiError('Phản hồi điểm tuần tra không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingAccountList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(item => item
    && typeof item.id === 'string' && typeof item.building_id === 'string' && typeof item.account_number === 'string')) {
    throw new ApiError('Phản hồi tài khoản thu phí không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingPolicies(payload, correlationId = '') {
  const validVersion = value => value && typeof value.id === 'string' && Number.isInteger(value.version_number)
    && typeof value.effective_from === 'string' && Number.isInteger(value.unit_rate_vnd)
    && Number.isInteger(value.rounding_unit_vnd);
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(item => item
    && typeof item.id === 'string' && typeof item.building_id === 'string' && typeof item.code === 'string'
    && Array.isArray(item.versions) && item.versions.every(validVersion))) {
    throw new ApiError('Phản hồi chính sách phí không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingPeriods(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.building_id === 'string'
    && typeof item.period_key === 'string' && typeof item.cutoff_at === 'string' && Number.isInteger(item.version);
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi kỳ kế toán không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingRuns(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.accounting_period_id === 'string'
    && typeof item.fee_policy_version_id === 'string' && typeof item.status === 'string'
    && Number.isInteger(item.retry_count) && Number.isInteger(item.version);
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi Billing Run không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingInvoices(payload, correlationId = '') {
  const validItem = item => item && typeof item.id === 'string' && Number.isInteger(item.line_number)
    && typeof item.description === 'string' && Number.isInteger(item.amount_vnd);
  const valid = item => item && typeof item.id === 'string' && typeof item.invoice_number === 'string'
    && typeof item.status === 'string' && Number.isInteger(item.total_vnd) && Number.isInteger(item.outstanding_vnd)
    && Array.isArray(item.items) && item.items.every(validItem);
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi hóa đơn không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertBillingPayment(item, correlationId = '') {
  const statuses = new Set(['RECEIVED', 'ALLOCATING', 'PARTIALLY_ALLOCATED', 'ALLOCATED', 'UNMATCHED', 'OVERPAID', 'REVERSED']);
  if (!item || typeof item.id !== 'string' || (item.billing_account_id !== null && typeof item.billing_account_id !== 'string')
    || typeof item.accounting_period_id !== 'string' || typeof item.building_id !== 'string'
    || typeof item.source_reference !== 'string' || typeof item.receipt_number !== 'string'
    || !Number.isInteger(item.amount_vnd) || typeof item.received_at !== 'string' || !statuses.has(item.status)) {
    throw new ApiError('Phản hồi payment không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return item;
}

function assertBillingPaymentList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) throw new ApiError('Phản hồi danh sách payment không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  payload.items.forEach(item => assertBillingPayment(item, correlationId));
  return payload;
}

function assertUnmatchedPayments(payload, correlationId = '') {
  const statuses = new Set(['OPEN', 'RESOLVED', 'REFUNDED']);
  const valid = item => item && typeof item.id === 'string' && typeof item.payment_id === 'string'
    && typeof item.building_id === 'string' && Number.isInteger(item.amount_vnd) && typeof item.reason === 'string'
    && statuses.has(item.status) && typeof item.source_reference === 'string' && typeof item.receipt_number === 'string';
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi hàng đợi unmatched không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertOverpaymentCredits(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.billing_account_id === 'string'
    && typeof item.payment_id === 'string' && Number.isInteger(item.original_vnd) && Number.isInteger(item.remaining_vnd)
    && ['OPEN', 'EXHAUSTED', 'VOID'].includes(item.status);
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi Overpayment Credit không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertPaymentAllocationResult(payload, correlationId = '') {
  const validAllocation = item => item && typeof item.id === 'string' && typeof item.payment_id === 'string'
    && typeof item.billing_invoice_id === 'string' && Number.isInteger(item.amount_vnd);
  if (!payload || !Array.isArray(payload.allocations) || !payload.allocations.every(validAllocation)) {
    throw new ApiError('Phản hồi phân bổ payment không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  assertBillingPayment(payload.payment, correlationId);
  if (payload.overpayment_credit !== null) assertOverpaymentCredits({ items: [payload.overpayment_credit] }, correlationId);
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

  async function request(path, { method = 'GET', body, signal, authenticated = true, idempotencyKey } = {}) {
    const requestCorrelationId = correlationIdFactory?.() || '';
    const requestRevision = sessionRevision;
    const requestToken = accessToken;
    const headers = { Accept: 'application/json' };
    if (requestCorrelationId) headers['X-Correlation-ID'] = requestCorrelationId;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
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

    async listBillingAccounts({ signal } = {}) {
      const result = await request('/billing/accounts', { signal });
      return assertBillingAccountList(result.payload, result.correlationId);
    },

    async listBillingFeePolicies({ signal } = {}) {
      const result = await request('/billing/fee-policies', { signal });
      return assertBillingPolicies(result.payload, result.correlationId);
    },

    async createBillingFeePolicy(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when creating a fee policy');
      const result = await request('/billing/fee-policies', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          building_id: values?.building_id, code: values?.code, name: values?.name,
          effective_from: values?.effective_from, unit_rate_vnd: values?.unit_rate_vnd,
          rounding_unit_vnd: values?.rounding_unit_vnd,
        },
      });
      return assertBillingPolicies({ items: [result.payload] }, result.correlationId).items[0];
    },

    async listAccountingPeriods({ signal } = {}) {
      const result = await request('/billing/periods', { signal });
      return assertBillingPeriods(result.payload, result.correlationId);
    },

    async createAccountingPeriod(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when creating an accounting period');
      const result = await request('/billing/periods', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          building_id: values?.building_id, period_key: values?.period_key, period_start: values?.period_start,
          period_end: values?.period_end, cutoff_at: values?.cutoff_at,
        },
      });
      return assertBillingPeriods({ items: [result.payload] }, result.correlationId).items[0];
    },

    async listBillingRuns({ signal } = {}) {
      const result = await request('/billing/runs', { signal });
      return assertBillingRuns(result.payload, result.correlationId);
    },

    async startBillingRun(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when starting a billing run');
      const result = await request('/billing/runs', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          accounting_period_id: values?.accounting_period_id,
          fee_policy_version_id: values?.fee_policy_version_id,
          run_key: values?.run_key,
        },
      });
      return assertBillingRuns({ items: [result.payload] }, result.correlationId).items[0];
    },

    async retryBillingRun(runId, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when retrying a billing run');
      const result = await request(`/billing/runs/${encodeURIComponent(runId)}/retry`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(),
      });
      return assertBillingRuns({ items: [result.payload] }, result.correlationId).items[0];
    },

    async listBillingInvoices({ signal } = {}) {
      const result = await request('/billing/invoices', { signal });
      return assertBillingInvoices(result.payload, result.correlationId);
    },

    async listBillingPayments({ signal } = {}) {
      const result = await request('/billing/payments', { signal });
      return assertBillingPaymentList(result.payload, result.correlationId);
    },

    async createBillingPayment(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when receiving a payment');
      const body = {
        accounting_period_id: values?.accounting_period_id, payment_source: values?.payment_source,
        source_reference: values?.source_reference, receipt_number: values?.receipt_number,
        amount_vnd: values?.amount_vnd, received_at: values?.received_at,
      };
      if (values?.billing_account_id) body.billing_account_id = values.billing_account_id;
      else body.building_id = values?.building_id;
      const result = await request('/billing/payments', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body,
      });
      return assertBillingPayment(result.payload, result.correlationId);
    },

    async listUnmatchedPayments({ signal } = {}) {
      const result = await request('/billing/unmatched-payments', { signal });
      return assertUnmatchedPayments(result.payload, result.correlationId);
    },

    async matchUnmatchedPayment(unmatchedPaymentId, billingAccountId, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when matching a payment');
      const result = await request(`/billing/unmatched-payments/${encodeURIComponent(unmatchedPaymentId)}/match`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: { billing_account_id: billingAccountId },
      });
      return assertBillingPayment(result.payload, result.correlationId);
    },

    async allocateBillingPayment(paymentId, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when allocating a payment');
      const result = await request(`/billing/payments/${encodeURIComponent(paymentId)}/allocate`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(),
      });
      return assertPaymentAllocationResult(result.payload, result.correlationId);
    },

    async listOverpaymentCredits({ signal } = {}) {
      const result = await request('/billing/overpayment-credits', { signal });
      return assertOverpaymentCredits(result.payload, result.correlationId);
    },

    async getServiceRequestFormOptions({ buildingId, signal } = {}) {
      const query = new URLSearchParams();
      if (buildingId) query.set('building_id', buildingId);
      const suffix = query.size ? `?${query}` : '';
      const result = await request(`/service-request-form-options${suffix}`, { signal });
      return assertServiceRequestFormOptions(result.payload, result.correlationId);
    },

    async createServiceRequest(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when creating a service request');
      }
      const body = {
        category_id: values?.category_id,
        building_id: values?.building_id,
        unit_id: values?.unit_id || null,
        title: values?.title,
        description: values?.description,
        priority: values?.priority,
      };
      const result = await request('/service-requests', {
        method: 'POST', body, signal, idempotencyKey: idempotencyKey.trim(),
      });
      return assertCreatedServiceRequest(result.payload, result.correlationId);
    },

    async getUnit360(unitId, { signal } = {}) {
      const result = await request(`/units/${encodeURIComponent(unitId)}/360`, { signal });
      return assertUnit360(result.payload, result.correlationId);
    },

    async listCleaningTasks({ signal } = {}) {
      const result = await request('/cleaning/tasks', { signal });
      return assertCleaningTaskList(result.payload, result.correlationId);
    },

    async listCleaningRoutes({ signal } = {}) {
      const result = await request('/cleaning/routes', { signal });
      return assertCleaningRoutes(result.payload, result.correlationId);
    },

    async listCleaningAssignees(buildingId, { signal } = {}) {
      const result = await request(`/cleaning/assignees?building_id=${encodeURIComponent(buildingId)}`, { signal });
      return assertCleaningAssignees(result.payload, result.correlationId);
    },

    async createCleaningShift(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when creating a cleaning shift');
      const result = await request('/cleaning/shifts', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          route_id: values?.route_id,
          scheduled_start_at: values?.scheduled_start_at,
          scheduled_end_at: values?.scheduled_end_at,
        },
      });
      if (!result.payload || !Array.isArray(result.payload.tasks)) throw new ApiError('Phản hồi tạo ca vệ sinh không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId: result.correlationId });
      result.payload.tasks.forEach(item => assertCleaningTask(item, result.correlationId));
      return result.payload;
    },

    async assignCleaningTask(taskId, values, { signal } = {}) {
      const result = await request(`/cleaning/tasks/${encodeURIComponent(taskId)}/assign`, {
        method: 'POST', signal, body: { assignee_id: values?.assignee_id, expected_version: values?.expected_version },
      });
      return assertCleaningTask(result.payload, result.correlationId);
    },

    async startCleaningTask(taskId, expectedVersion, { signal } = {}) {
      const result = await request(`/cleaning/tasks/${encodeURIComponent(taskId)}/start`, {
        method: 'POST', signal, body: { expected_version: expectedVersion },
      });
      return assertCleaningTask(result.payload, result.correlationId);
    },

    async updateCleaningChecklist(taskId, itemId, values, { signal } = {}) {
      const result = await request(`/cleaning/tasks/${encodeURIComponent(taskId)}/checklist/${encodeURIComponent(itemId)}`, {
        method: 'PATCH', signal, body: {
          expected_version: values?.expected_version,
          result: values?.result,
          note: values?.note || null,
        },
      });
      return assertCleaningTask(result.payload, result.correlationId);
    },

    async submitCleaningTask(taskId, expectedVersion, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when submitting a cleaning task');
      const result = await request(`/cleaning/tasks/${encodeURIComponent(taskId)}/submit`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: { expected_version: expectedVersion },
      });
      return assertCleaningTask(result.payload, result.correlationId);
    },

    async acceptCleaningTask(taskId, expectedVersion, { signal } = {}) {
      const result = await request(`/cleaning/tasks/${encodeURIComponent(taskId)}/accept`, {
        method: 'POST', signal, body: { expected_version: expectedVersion },
      });
      return assertCleaningTask(result.payload, result.correlationId);
    },

    async listSecurityDashboard({ signal } = {}) {
      const result = await request('/security/dashboard', { signal });
      return assertSecurityDashboard(result.payload, result.correlationId);
    },

    async listSecurityPatrolPoints({ signal } = {}) {
      const result = await request('/security/patrol-points', { signal });
      return assertSecurityPoints(result.payload, result.correlationId);
    },

    async listSecurityAssignees(buildingId, { signal } = {}) {
      const result = await request(`/security/assignees?building_id=${encodeURIComponent(buildingId)}`, { signal });
      return assertCleaningAssignees(result.payload, result.correlationId);
    },

    async createSecurityShift(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when creating a security shift');
      const result = await request('/security/shifts', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          building_id: values?.building_id,
          assignee_id: values?.assignee_id,
          scheduled_start_at: values?.scheduled_start_at,
          scheduled_end_at: values?.scheduled_end_at,
          patrol_windows: values?.patrol_windows,
        },
      });
      return assertSecurityShift(result.payload, result.correlationId);
    },

    async startSecurityShift(shiftId, expectedVersion, { signal } = {}) {
      const result = await request(`/security/shifts/${encodeURIComponent(shiftId)}/start`, {
        method: 'POST', signal, body: { expected_version: expectedVersion },
      });
      return assertSecurityShift(result.payload, result.correlationId);
    },

    async createSecurityHandoff(shiftId, values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when recording a handoff');
      const result = await request(`/security/shifts/${encodeURIComponent(shiftId)}/handoffs`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          received_by_id: values?.received_by_id,
          summary: values?.summary,
        },
      });
      return assertSecurityShift(result.payload, result.correlationId);
    },

    async createSecurityVisitor(shiftId, values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when recording a visitor');
      const result = await request(`/security/shifts/${encodeURIComponent(shiftId)}/visitors`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          visitor_name: values?.visitor_name,
          visit_purpose: values?.visit_purpose,
          document_reference: values?.document_reference || null,
          checked_in_at: values?.checked_in_at,
        },
      });
      return assertSecurityShift(result.payload, result.correlationId);
    },

    async createPatrolLog(windowId, values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when recording a patrol log');
      const result = await request(`/security/patrol-windows/${encodeURIComponent(windowId)}/logs`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          event_type: values?.event_type,
          note: values?.note || null,
          occurred_at: values?.occurred_at,
        },
      });
      return assertSecurityPatrolWindow(result.payload, result.correlationId);
    },

    async completePatrolWindow(windowId, values, { signal } = {}) {
      const result = await request(`/security/patrol-windows/${encodeURIComponent(windowId)}/complete`, {
        method: 'POST', signal, body: { expected_version: values?.expected_version, note: values?.note || null },
      });
      return assertSecurityPatrolWindow(result.payload, result.correlationId);
    },

    async missPatrolWindow(windowId, values, { signal } = {}) {
      const result = await request(`/security/patrol-windows/${encodeURIComponent(windowId)}/missed`, {
        method: 'POST', signal, body: { expected_version: values?.expected_version, reason: values?.reason },
      });
      return assertSecurityPatrolWindow(result.payload, result.correlationId);
    },

    async createSecurityIncident(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when creating an incident');
      const result = await request('/security/incidents', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          patrol_window_id: values?.patrol_window_id,
          incident_type: values?.incident_type,
          severity: values?.severity,
          title: values?.title,
          description: values?.description,
          occurred_at: values?.occurred_at,
        },
      });
      return assertSecurityIncident(result.payload, result.correlationId);
    },

    async addSecurityIncidentEvidence(incidentId, values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when recording evidence');
      const result = await request(`/security/incidents/${encodeURIComponent(incidentId)}/evidence`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          evidence_type: values?.evidence_type,
          description: values?.description,
          storage_reference: values?.storage_reference || null,
        },
      });
      return assertSecurityIncident(result.payload, result.correlationId);
    },

    async acknowledgeSecurityEscalation(incidentId, escalationId, note, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) throw new TypeError('idempotencyKey is required when acknowledging an escalation');
      const result = await request(`/security/incidents/${encodeURIComponent(incidentId)}/escalations/${encodeURIComponent(escalationId)}/acknowledgements`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: { note: note || null },
      });
      return assertSecurityIncident(result.payload, result.correlationId);
    },

    async transitionSecurityIncident(incidentId, values, { signal } = {}) {
      const result = await request(`/security/incidents/${encodeURIComponent(incidentId)}/transition`, {
        method: 'POST', signal, body: {
          expected_version: values?.expected_version,
          status: values?.status,
          conclusion: values?.conclusion || null,
        },
      });
      return assertSecurityIncident(result.payload, result.correlationId);
    },

    clearSession,
    hasSession: () => Boolean(accessToken),
  };
}

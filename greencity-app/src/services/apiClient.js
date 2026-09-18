export const resolveApiBaseUrl = value => String(value ?? '').trim() || '/api/v1';

const configuredBaseUrl = import.meta.env?.VITE_API_BASE_URL;
const DEFAULT_BASE_URL = resolveApiBaseUrl(configuredBaseUrl);

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

const PARCEL_STATUSES = new Set([
  'RECEIVED', 'READY_FOR_PICKUP', 'HANDED_OVER', 'RETURNED', 'LOST', 'DAMAGED',
]);

function assertParcel(payload, correlationId = '') {
  const requiredStrings = [
    'id', 'tenant_id', 'site_id', 'building_id', 'unit_id', 'parcel_code',
    'recipient_name_snapshot', 'status', 'received_at', 'created_at', 'updated_at',
  ];
  const nullableStrings = [
    'recipient_person_id', 'carrier_reference', 'recipient_contact_snapshot',
    'storage_location', 'pin_locked_until', 'ready_for_pickup_at', 'handed_over_at',
    'handed_over_by_id', 'exception_reason', 'created_by_id', 'updated_by_id',
  ];
  if (!payload || requiredStrings.some(field => typeof payload[field] !== 'string')
    || !PARCEL_STATUSES.has(payload.status) || !Number.isInteger(payload.version)
    || !Number.isInteger(payload.pin_attempt_count)
    || nullableStrings.some(field => payload[field] !== null && typeof payload[field] !== 'string')) {
    throw new ApiError('Phản hồi bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertParcelList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items) || !Number.isInteger(payload.page)
    || !Number.isInteger(payload.page_size) || !Number.isInteger(payload.total)) {
    throw new ApiError('Phản hồi danh sách bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertParcel(item, correlationId));
  return payload;
}

const CASE_STATUSES = new Set(['NEW', 'TRIAGED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED']);
const INCIDENT_TYPES = new Set(['SECURITY', 'FIRE']);
const INCIDENT_SEVERITIES = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);

function assertParcelCase(payload, correlationId = '') {
  const strings = ['id', 'building_id', 'reason', 'created_by_id', 'updated_by_id', 'created_at', 'updated_at'];
  if (!payload || strings.some(field => typeof payload[field] !== 'string')
    || (payload.source_work_order_id !== null && typeof payload.source_work_order_id !== 'string')
    || (payload.source_parcel_id !== null && typeof payload.source_parcel_id !== 'string')
    || !CASE_STATUSES.has(payload.status) || !Number.isInteger(payload.version)) {
    throw new ApiError('Phản hồi Case bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertParcelIncident(payload, correlationId = '') {
  const strings = ['id', 'building_id', 'code', 'title', 'description', 'occurred_at', 'reported_by_id'];
  if (!payload || strings.some(field => typeof payload[field] !== 'string')
    || (payload.parcel_id !== null && typeof payload.parcel_id !== 'string')
    || (payload.patrol_window_id !== null && typeof payload.patrol_window_id !== 'string')
    || !INCIDENT_TYPES.has(payload.incident_type) || !INCIDENT_SEVERITIES.has(payload.severity)
    || !CASE_STATUSES.has(payload.status) || !Number.isInteger(payload.version)) {
    throw new ApiError('Phản hồi incident bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertParcelEvidence(payload, correlationId = '') {
  if (!payload || typeof payload.id !== 'string' || typeof payload.parcel_id !== 'string'
    || typeof payload.original_name !== 'string' || typeof payload.mime_type !== 'string'
    || !Number.isInteger(payload.size_bytes) || typeof payload.sha256 !== 'string'
    || typeof payload.created_at !== 'string') {
    throw new ApiError('Phản hồi bằng chứng bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertParcelEvidenceList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách bằng chứng bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertParcelEvidence(item, correlationId));
  return payload;
}

function assertParcelTimeline(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.event_type === 'string'
    && typeof item.action === 'string' && typeof item.resource_type === 'string'
    && typeof item.resource_id === 'string' && typeof item.correlation_id === 'string'
    && typeof item.created_at === 'string'
    && (item.reason === null || typeof item.reason === 'string')
    && (item.before_data === null || typeof item.before_data === 'object')
    && (item.after_data === null || typeof item.after_data === 'object');
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi timeline bưu phẩm không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

const RESIDENT_REQUEST_STATUSES = new Set(['NEW', 'TRIAGED', 'IN_PROGRESS', 'WAITING_INFO', 'RESOLVED', 'CLOSED', 'CANCELLED']);

function assertResidentServiceRequest(payload, correlationId = '') {
  const strings = ['id', 'code', 'unit_id', 'category_id', 'title', 'description', 'priority', 'status', 'sla_deadline', 'created_at', 'updated_at'];
  if (!payload || strings.some(field => typeof payload[field] !== 'string')
    || !RESIDENT_REQUEST_STATUSES.has(payload.status) || !Number.isInteger(payload.version)
    || (payload.sla_breached_at !== null && typeof payload.sla_breached_at !== 'string')
    || (payload.resolved_at !== null && typeof payload.resolved_at !== 'string')
    || (payload.closed_at !== null && typeof payload.closed_at !== 'string')) {
    throw new ApiError('Phản hồi yêu cầu cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentServiceRequestList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items) || !Number.isInteger(payload.page)
    || !Number.isInteger(payload.page_size) || !Number.isInteger(payload.total)) {
    throw new ApiError('Phản hồi danh sách yêu cầu cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertResidentServiceRequest(item, correlationId));
  return payload;
}

function assertResidentTimeline(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.event_type === 'string'
    && typeof item.action === 'string' && typeof item.created_at === 'string'
    && (item.before_status === null || typeof item.before_status === 'string')
    && (item.after_status === null || typeof item.after_status === 'string')
    && (item.before_priority === null || typeof item.before_priority === 'string')
    && (item.after_priority === null || typeof item.after_priority === 'string');
  if (!payload || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi lịch sử yêu cầu cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentEvidence(payload, correlationId = '') {
  if (!payload || typeof payload.id !== 'string' || typeof payload.original_name !== 'string'
    || typeof payload.mime_type !== 'string' || !Number.isInteger(payload.size_bytes)
    || typeof payload.sha256 !== 'string' || typeof payload.created_at !== 'string') {
    throw new ApiError('Phản hồi bằng chứng cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentEvidenceList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách bằng chứng cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertResidentEvidence(item, correlationId));
  return payload;
}

function assertResidentSignedLink(payload, correlationId = '') {
  if (!payload || typeof payload.url !== 'string' || typeof payload.expires_at !== 'string') {
    throw new ApiError('Phản hồi liên kết bằng chứng cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentBillingSummary(payload, correlationId = '') {
  const valid = item => item && typeof item.unit_id === 'string' && Number.isInteger(item.ar_balance_vnd);
  if (!payload || typeof payload.as_of !== 'string' || !Number.isInteger(payload.total_ar_balance_vnd)
    || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi tổng quan công nợ cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentBillingInvoices(payload, correlationId = '') {
  const validItem = item => item && Number.isInteger(item.line_number) && typeof item.description === 'string'
    && typeof item.basis === 'string' && Number.isFinite(item.basis_quantity)
    && Number.isInteger(item.unit_rate_vnd_snapshot) && Number.isInteger(item.rounding_unit_vnd_snapshot)
    && Number.isInteger(item.amount_vnd);
  const valid = item => item && typeof item.id === 'string' && typeof item.unit_id === 'string'
    && typeof item.invoice_number === 'string' && typeof item.issued_on === 'string'
    && (item.due_on === null || typeof item.due_on === 'string') && Number.isInteger(item.total_vnd)
    && Array.isArray(item.items) && item.items.every(validItem);
  if (!payload || typeof payload.as_of !== 'string' || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi hóa đơn cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentBillingPayments(payload, correlationId = '') {
  const valid = item => item && typeof item.id === 'string' && typeof item.unit_id === 'string'
    && typeof item.payment_source === 'string' && typeof item.receipt_number === 'string'
    && Number.isInteger(item.amount_vnd) && typeof item.received_at === 'string';
  if (!payload || typeof payload.as_of !== 'string' || !Array.isArray(payload.items) || !payload.items.every(valid)) {
    throw new ApiError('Phản hồi payment cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload;
}

function assertResidentNotification(item, correlationId = '') {
  const statuses = new Set(['PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'PUBLISHED', 'DEAD_LETTER']);
  if (!item || typeof item.id !== 'string' || typeof item.template_code !== 'string'
    || typeof item.template_snapshot !== 'object' || item.template_snapshot === null
    || !statuses.has(item.delivery_status) || typeof item.correlation_id !== 'string'
    || typeof item.created_at !== 'string'
    || (item.delivered_at !== null && typeof item.delivered_at !== 'string')
    || (item.read_at !== null && typeof item.read_at !== 'string')) {
    throw new ApiError('Phản hồi thông báo cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return item;
}

function assertResidentNotificationList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items) || !Number.isInteger(payload.page)
    || !Number.isInteger(payload.page_size) || !Number.isInteger(payload.total)
    || !Number.isInteger(payload.unread_count)) {
    throw new ApiError('Phản hồi hộp thư cư dân không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  payload.items.forEach(item => assertResidentNotification(item, correlationId));
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

function assertNotification(item, correlationId = '') {
  const statuses = new Set(['PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'PUBLISHED', 'DEAD_LETTER']);
  if (!item || typeof item.id !== 'string' || typeof item.domain_event_id !== 'string'
    || typeof item.template_code !== 'string' || typeof item.template_snapshot !== 'object'
    || item.template_snapshot === null || !statuses.has(item.delivery_status)
    || typeof item.created_at !== 'string') {
    throw new ApiError('Phản hồi thông báo không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return item;
}

function assertNotificationList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách thông báo không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.items.forEach(item => assertNotification(item, correlationId));
  return payload;
}

function assertOutboxEvent(item, correlationId = '') {
  const statuses = new Set(['PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'PUBLISHED', 'DEAD_LETTER']);
  if (!item || typeof item.id !== 'string' || typeof item.event_type !== 'string'
    || typeof item.resource_type !== 'string' || typeof item.resource_id !== 'string'
    || typeof item.correlation_id !== 'string' || !statuses.has(item.delivery_status)
    || !Number.isInteger(item.attempt_count) || typeof item.next_attempt_at !== 'string'
    || typeof item.created_at !== 'string') {
    throw new ApiError('Phản hồi sự kiện outbox không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return item;
}

function assertOutboxEventList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách outbox không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.items.forEach(item => assertOutboxEvent(item, correlationId));
  return payload;
}

function assertDashboardView(payload, correlationId = '') {
  if (!payload || typeof payload.as_of !== 'string'
    || !Number.isInteger(payload.sla_overdue_count)
    || !Number.isInteger(payload.maintenance_due_count)
    || !Number.isInteger(payload.cleaning_rework_count)
    || !Number.isInteger(payload.open_incident_count)
    || !Number.isInteger(payload.ar_debt_vnd)) {
    throw new ApiError('Phản hồi Dashboard KPI không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return payload;
}

function assertDashboardDrillDownItem(item, correlationId = '') {
  const metrics = new Set(['sla_overdue', 'maintenance_due', 'cleaning_rework', 'open_incidents', 'ar_debt']);
  if (!item || typeof item.metric !== 'string' || !metrics.has(item.metric)
    || typeof item.resource_type !== 'string' || typeof item.resource_id !== 'string'
    || typeof item.building_id !== 'string' || typeof item.reference !== 'string'
    || typeof item.title !== 'string' || typeof item.occurred_at !== 'string'
    || (item.amount_vnd !== null && item.amount_vnd !== undefined && !Number.isInteger(item.amount_vnd))) {
    throw new ApiError('Phản hồi chi tiết Drill-down không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return item;
}

function assertDashboardDrillDownResponse(payload, correlationId = '') {
  const metrics = new Set(['sla_overdue', 'maintenance_due', 'cleaning_rework', 'open_incidents', 'ar_debt']);
  if (!payload || typeof payload.as_of !== 'string' || !metrics.has(payload.metric) || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách Drill-down không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.items.forEach(item => assertDashboardDrillDownItem(item, correlationId));
  return payload;
}

function assertAuditEvent(item, correlationId = '') {
  if (!item || typeof item.id !== 'string' || typeof item.event_type !== 'string'
    || typeof item.action !== 'string' || typeof item.resource_type !== 'string'
    || typeof item.resource_id !== 'string' || typeof item.correlation_id !== 'string'
    || typeof item.created_at !== 'string') {
    throw new ApiError('Phản hồi sự kiện kiểm toán không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  return item;
}

function assertAuditEventList(payload, correlationId = '') {
  if (!payload || !Array.isArray(payload.items)) {
    throw new ApiError('Phản hồi danh sách sự kiện kiểm toán không đúng định dạng.', { code: 'ERR-INVALID-RESPONSE', correlationId });
  }
  payload.items.forEach(item => assertAuditEvent(item, correlationId));
  return payload;
}

function assertAssistantChatResponse(payload, correlationId = '') {
  if (!payload || typeof payload.reply !== 'string' || !payload.reply.trim()) {
    throw new ApiError('Phản hồi Green Assistant không đúng định dạng.', {
      code: 'ERR-INVALID-RESPONSE', correlationId,
    });
  }
  return payload.reply;
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

  async function request(path, {
    method = 'GET', body, rawBody, contentType, extraHeaders = {}, signal,
    authenticated = true, idempotencyKey,
  } = {}) {
    if (body !== undefined && rawBody !== undefined) throw new TypeError('body and rawBody are mutually exclusive');
    const requestCorrelationId = correlationIdFactory?.() || '';
    const requestRevision = sessionRevision;
    const requestToken = accessToken;
    const headers = { Accept: 'application/json' };
    if (requestCorrelationId) headers['X-Correlation-ID'] = requestCorrelationId;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (rawBody !== undefined) headers['Content-Type'] = contentType || 'application/octet-stream';
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    if (authenticated && requestToken) headers.Authorization = `Bearer ${requestToken}`;
    Object.assign(headers, extraHeaders);
    const requestBody = rawBody !== undefined
      ? rawBody
      : body === undefined ? undefined : JSON.stringify(body);

    let response;
    try {
      response = await fetchImpl(`${apiBaseUrl}${path}`, {
        method, headers, signal, body: requestBody,
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

  async function getParcelEvidenceLink(parcelId, attachmentId, { signal } = {}) {
    if (!parcelId || !attachmentId) throw new TypeError('parcelId and attachmentId are required');
    const result = await request(`/parcels/${encodeURIComponent(parcelId)}/evidence/${encodeURIComponent(attachmentId)}/signed-link`, { signal });
    if (!result.payload || typeof result.payload.url !== 'string' || typeof result.payload.expires_at !== 'string') {
      throw new ApiError('Phản hồi liên kết bằng chứng bưu phẩm không đúng định dạng.', {
        code: 'ERR-INVALID-RESPONSE', correlationId: result.correlationId,
      });
    }
    return result.payload;
  }

  return {
    async chatAssistant(message, { signal } = {}) {
      if (typeof message !== 'string' || !message.trim()) throw new TypeError('message must be a non-empty string');
      const result = await request('/assistant/chat', {
        method: 'POST',
        body: { message: message.trim() },
        signal,
      });
      return assertAssistantChatResponse(result.payload, result.correlationId);
    },

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

    async listParcels({ status, buildingId, page = 1, page_size = 50, signal } = {}) {
      const query = new URLSearchParams({ page: String(page), page_size: String(page_size) });
      if (status) query.set('status', status);
      if (buildingId) query.set('building_id', buildingId);
      const result = await request(`/parcels?${query}`, { signal });
      return assertParcelList(result.payload, result.correlationId);
    },

    async createParcel(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when receiving a parcel');
      }
      const body = {
        building_id: values?.building_id,
        unit_id: values?.unit_id,
        recipient_person_id: values?.recipient_person_id || null,
        parcel_code: values?.parcel_code,
        carrier_reference: values?.carrier_reference || null,
        recipient_name_snapshot: values?.recipient_name_snapshot,
        recipient_contact_snapshot: values?.recipient_contact_snapshot || null,
        storage_location: values?.storage_location || null,
        pin: values?.pin,
      };
      if (values?.received_at) body.received_at = values.received_at;
      const result = await request('/parcels', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body,
      });
      return assertParcel(result.payload, result.correlationId);
    },

    async markParcelReady(parcelId, expectedVersion, { idempotencyKey, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when marking a parcel ready');
      }
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/ready`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(),
        body: { expected_version: expectedVersion },
      });
      return assertParcel(result.payload, result.correlationId);
    },

    async handoverParcel(parcelId, values, { idempotencyKey, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when handing over a parcel');
      }
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/handover`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          expected_version: values?.expected_version,
          pin: values?.pin,
        },
      });
      return assertParcel(result.payload, result.correlationId);
    },

    async recordParcelException(parcelId, values, { idempotencyKey, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when recording a parcel exception');
      }
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/exception`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          expected_version: values?.expected_version,
          status: values?.status,
          reason: values?.reason,
        },
      });
      return assertParcel(result.payload, result.correlationId);
    },

    async getParcelCase(parcelId, { signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/case`, { signal });
      return assertParcelCase(result.payload, result.correlationId);
    },

    async openParcelCase(parcelId, reason, { idempotencyKey, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when opening a parcel case');
      }
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/case`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: { reason },
      });
      return assertParcelCase(result.payload, result.correlationId);
    },

    async getParcelIncident(parcelId, { signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/incident`, { signal });
      return assertParcelIncident(result.payload, result.correlationId);
    },

    async linkParcelIncident(parcelId, values, { idempotencyKey, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when linking a parcel incident');
      }
      const reason = typeof values?.reason === 'string' ? values.reason.trim() : '';
      const body = { incident_id: values?.incident_id };
      if (reason) body.reason = reason;
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/incident-link`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body,
      });
      return assertParcelIncident(result.payload, result.correlationId);
    },

    async listParcelEvidence(parcelId, { signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/evidence`, { signal });
      return assertParcelEvidenceList(result.payload, result.correlationId);
    },

    async uploadParcelEvidence(parcelId, rawBody, { idempotencyKey, fileName, contentType, signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when uploading parcel evidence');
      }
      const extraHeaders = {};
      if (fileName) extraHeaders['X-File-Name'] = fileName;
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/evidence`, {
        method: 'POST', signal, rawBody, contentType: contentType || 'application/octet-stream',
        extraHeaders, idempotencyKey: idempotencyKey.trim(),
      });
      return assertParcelEvidence(result.payload, result.correlationId);
    },

    async getParcelEvidenceLink(parcelId, attachmentId, { signal } = {}) {
      return getParcelEvidenceLink(parcelId, attachmentId, { signal });
    },

    async downloadParcelEvidence(parcelId, attachmentId, { signal } = {}) {
      if (!parcelId || !attachmentId) throw new TypeError('parcelId and attachmentId are required');
      const signed = await getParcelEvidenceLink(parcelId, attachmentId, { signal });
      const requestCorrelationId = correlationIdFactory?.() || '';
      const requestRevision = sessionRevision;
      const requestToken = accessToken;
      const headers = { Accept: 'image/png, image/jpeg, application/octet-stream' };
      if (requestCorrelationId) headers['X-Correlation-ID'] = requestCorrelationId;
      if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
      let response;
      try {
        const signedUrl = /^https?:\/\//i.test(signed.url)
          ? signed.url
          : (/^https?:\/\//i.test(apiBaseUrl)
            ? new URL(signed.url, new URL(apiBaseUrl).origin).toString()
            : signed.url);
        response = await fetchImpl(signedUrl, { method: 'GET', headers, signal });
      } catch (cause) {
        if (requestRevision !== sessionRevision) throw staleSessionError();
        if (cause?.name === 'AbortError') throw cause;
        throw new ApiError('Không thể tải bằng chứng private. Kiểm tra mạng rồi thử lại.', {
          code: 'ERR-NETWORK', correlationId: requestCorrelationId, cause,
        });
      }
      if (requestRevision !== sessionRevision) throw staleSessionError();
      if (!response.ok) {
        const payload = await readPayload(response);
        const error = errorFromResponse(response, payload, response.headers?.get?.('X-Correlation-ID') || requestCorrelationId);
        if (response.status === 401) {
          const isCurrentSession = requestRevision === sessionRevision && requestToken === accessToken;
          if (isCurrentSession && requestToken) {
            clearSession();
            onUnauthorized(error);
          }
        }
        throw error;
      }
      if (typeof response.blob !== 'function') {
        throw new ApiError('Phản hồi bằng chứng private không hỗ trợ xem nội dung.', {
          code: 'ERR-INVALID-RESPONSE', correlationId: requestCorrelationId,
        });
      }
      const blob = await response.blob();
      if (requestRevision !== sessionRevision) throw staleSessionError();
      return {
        blob,
        contentType: response.headers?.get?.('content-type') || blob.type || 'application/octet-stream',
        correlationId: response.headers?.get?.('X-Correlation-ID') || requestCorrelationId,
      };
    },

    async getParcelTimeline(parcelId, { signal } = {}) {
      if (!parcelId) throw new TypeError('parcelId is required');
      const result = await request(`/parcels/${encodeURIComponent(parcelId)}/timeline`, { signal });
      return assertParcelTimeline(result.payload, result.correlationId);
    },

    async listServiceRequests({ status, page = 1, page_size = 20, signal } = {}) {
      const query = new URLSearchParams();
      if (status) query.set('status', status);
      query.set('page', String(page));
      query.set('page_size', String(page_size));
      const result = await request(`/service-requests?${query}`, { signal });
      return assertServiceRequestList(result.payload, result.correlationId);
    },

    async getResidentServiceRequestOptions({ signal } = {}) {
      const result = await request('/resident/service-request-options', { signal });
      return assertServiceRequestFormOptions(result.payload, result.correlationId);
    },

    async listResidentServiceRequests({ page = 1, page_size = 20, signal } = {}) {
      const query = new URLSearchParams({ page: String(page), page_size: String(page_size) });
      const result = await request(`/resident/service-requests?${query}`, { signal });
      return assertResidentServiceRequestList(result.payload, result.correlationId);
    },

    async getResidentServiceRequest(requestId, { signal } = {}) {
      if (!requestId) throw new TypeError('requestId is required');
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}`, { signal });
      return assertResidentServiceRequest(result.payload, result.correlationId);
    },

    async createResidentServiceRequest(values, { idempotencyKey, signal } = {}) {
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when creating a resident service request');
      }
      const result = await request('/resident/service-requests', {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), body: {
          unit_id: values?.unit_id,
          category_id: values?.category_id,
          title: values?.title,
          description: values?.description,
          priority: values?.priority || 'MEDIUM',
        },
      });
      return assertResidentServiceRequest(result.payload, result.correlationId);
    },

    async updateResidentServiceRequest(requestId, values, { idempotencyKey, signal } = {}) {
      if (!requestId) throw new TypeError('requestId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when updating a resident service request');
      }
      const body = { expected_version: values?.expected_version };
      for (const field of ['title', 'description', 'priority']) {
        if (values?.[field] !== undefined && values?.[field] !== null) body[field] = values[field];
      }
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}`, {
        method: 'PATCH', signal, idempotencyKey: idempotencyKey.trim(), body,
      });
      return assertResidentServiceRequest(result.payload, result.correlationId);
    },

    async getResidentServiceRequestTimeline(requestId, { signal } = {}) {
      if (!requestId) throw new TypeError('requestId is required');
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}/timeline`, { signal });
      return assertResidentTimeline(result.payload, result.correlationId);
    },

    async listResidentServiceRequestEvidence(requestId, { signal } = {}) {
      if (!requestId) throw new TypeError('requestId is required');
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}/evidence`, { signal });
      return assertResidentEvidenceList(result.payload, result.correlationId);
    },

    async uploadResidentServiceRequestEvidence(requestId, file, { idempotencyKey, signal } = {}) {
      if (!requestId) throw new TypeError('requestId is required');
      if (!file) throw new TypeError('file is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when uploading resident evidence');
      }
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}/evidence`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(), rawBody: file,
        contentType: file.type || 'application/octet-stream',
        extraHeaders: { 'X-File-Name': file.name || 'evidence' },
      });
      return assertResidentEvidence(result.payload, result.correlationId);
    },

    async getResidentEvidenceLink(requestId, attachmentId, { signal } = {}) {
      if (!requestId || !attachmentId) throw new TypeError('requestId and attachmentId are required');
      const result = await request(`/resident/service-requests/${encodeURIComponent(requestId)}/evidence/${encodeURIComponent(attachmentId)}/signed-link`, { signal });
      return assertResidentSignedLink(result.payload, result.correlationId);
    },

    async getResidentBillingSummary(asOf, { signal } = {}) {
      if (!asOf) throw new TypeError('asOf is required');
      const result = await request(`/resident/billing/summary?as_of=${encodeURIComponent(asOf)}`, { signal });
      return assertResidentBillingSummary(result.payload, result.correlationId);
    },

    async listResidentBillingInvoices(asOf, { signal } = {}) {
      if (!asOf) throw new TypeError('asOf is required');
      const result = await request(`/resident/billing/invoices?as_of=${encodeURIComponent(asOf)}`, { signal });
      return assertResidentBillingInvoices(result.payload, result.correlationId);
    },

    async listResidentBillingPayments(asOf, { signal } = {}) {
      if (!asOf) throw new TypeError('asOf is required');
      const result = await request(`/resident/billing/payments?as_of=${encodeURIComponent(asOf)}`, { signal });
      return assertResidentBillingPayments(result.payload, result.correlationId);
    },

    async listResidentNotifications({ includeRead = false, page = 1, page_size = 20, signal } = {}) {
      const query = new URLSearchParams({
        include_read: includeRead ? 'true' : 'false', page: String(page), page_size: String(page_size),
      });
      const result = await request(`/resident/notifications?${query}`, { signal });
      return assertResidentNotificationList(result.payload, result.correlationId);
    },

    async markResidentNotificationRead(notificationId, { signal } = {}) {
      if (!notificationId) throw new TypeError('notificationId is required');
      const result = await request(`/resident/notifications/${encodeURIComponent(notificationId)}/read`, {
        method: 'POST', signal,
      });
      return assertResidentNotification(result.payload, result.correlationId);
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

    async listNotifications({ includeRead = false, signal } = {}) {
      const query = includeRead ? '?include_read=true' : '';
      const result = await request(`/notifications${query}`, { signal });
      return assertNotificationList(result.payload, result.correlationId);
    },

    async markNotificationRead(notificationId, { idempotencyKey, signal } = {}) {
      if (!notificationId) throw new TypeError('notificationId is required');
      const result = await request(`/notifications/${encodeURIComponent(notificationId)}/read`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey?.trim?.() || undefined,
      });
      return assertNotification(result.payload, result.correlationId);
    },

    async listOutboxEvents({ deliveryStatus, limit = 50, offset = 0, signal } = {}) {
      const params = new URLSearchParams();
      if (deliveryStatus) params.set('delivery_status', deliveryStatus);
      if (limit) params.set('limit', String(limit));
      if (offset) params.set('offset', String(offset));
      const query = params.toString() ? `?${params.toString()}` : '';
      const result = await request(`/outbox/events${query}`, { signal });
      return assertOutboxEventList(result.payload, result.correlationId);
    },

    async retryOutboxEvent(eventId, { idempotencyKey, signal } = {}) {
      if (!eventId) throw new TypeError('eventId is required');
      if (typeof idempotencyKey !== 'string' || !idempotencyKey.trim()) {
        throw new TypeError('idempotencyKey is required when retrying an outbox event');
      }
      const result = await request(`/outbox/events/${encodeURIComponent(eventId)}/retry`, {
        method: 'POST', signal, idempotencyKey: idempotencyKey.trim(),
      });
      return assertOutboxEvent(result.payload, result.correlationId);
    },

    async getDashboard({ asOf, signal } = {}) {
      if (!asOf) throw new TypeError('asOf is required');
      const result = await request(`/dashboard?as_of=${encodeURIComponent(asOf)}`, { signal });
      return assertDashboardView(result.payload, result.correlationId);
    },

    async getDashboardDrillDown(metric, { asOf, signal } = {}) {
      if (!metric) throw new TypeError('metric is required');
      if (!asOf) throw new TypeError('asOf is required');
      const result = await request(`/dashboard/drill-down/${encodeURIComponent(metric)}?as_of=${encodeURIComponent(asOf)}`, { signal });
      return assertDashboardDrillDownResponse(result.payload, result.correlationId);
    },

    async listAuditEvents({ correlationId: corrId, resourceType, resourceId, asOf, limit = 50, offset = 0, signal } = {}) {
      const params = new URLSearchParams();
      if (corrId) params.set('correlation_id', corrId);
      if (resourceType) params.set('resource_type', resourceType);
      if (resourceId) params.set('resource_id', resourceId);
      if (asOf) params.set('as_of', asOf);
      if (limit) params.set('limit', String(limit));
      if (offset) params.set('offset', String(offset));
      const query = params.toString() ? `?${params.toString()}` : '';
      const result = await request(`/audit-events${query}`, { signal });
      return assertAuditEventList(result.payload, result.correlationId);
    },

    clearSession,
    hasSession: () => Boolean(accessToken),
  };
}

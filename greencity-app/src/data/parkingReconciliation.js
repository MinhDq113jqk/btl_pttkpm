export function parkingPeriod(form) {
  const start = new Date(form.starts_at); const end = new Date(form.ends_at);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) throw new Error('Cần nhập khoảng thời gian hợp lệ, thời điểm kết thúc sau bắt đầu.');
  return { starts_at: start.toISOString(), ends_at: end.toISOString() };
}

export function parkingUsagePayload(form, entries) {
  const period = parkingPeriod(form); const seen = new Set();
  return { resource_id: form.resource_id, source_reference: form.source_reference.trim(), completeness: form.completeness, ...period,
    entries: entries.map(entry => {
      const moment = new Date(entry.occurred_at);
      if (!Number.isFinite(moment.getTime()) || moment < new Date(period.starts_at) || moment >= new Date(period.ends_at)) throw new Error('Mỗi lượt phải nằm trong khoảng nguồn, trước thời điểm kết thúc.');
      const reference = entry.event_reference.trim();
      if (!reference || seen.has(reference)) throw new Error('Mã lượt sử dụng phải có giá trị và không trùng trong nguồn.');
      seen.add(reference);
      return { event_reference: reference, occurred_at: moment.toISOString(), plate: entry.plate.trim().toUpperCase().replaceAll(' ', ''), slot_code: entry.slot_code || null, unit_id: entry.unit_id || null, holder_account_id: entry.holder_account_id || null };
    }) };
}

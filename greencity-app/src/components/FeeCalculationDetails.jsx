import React from 'react';

const money = value => `${new Intl.NumberFormat('vi-VN').format(value)} đ`;

export function FeeCalculationDetails({ calculation }) {
  if (!calculation?.method || calculation.method === 'LEGACY') return null;
  const segments = calculation.line_key
    ? calculation.segments?.filter(row => row.key === calculation.line_key)
    : calculation.segments;
  return <details className="portal-terms">
    <summary>Căn cứ tính phí</summary>
    {calculation.method === 'ONE_TIME' ? <p>Khoản phí một lần: {money(calculation.amount_vnd)}.</p> : <>
      <p>Kỳ {calculation.period_start} → {calculation.period_end}: {calculation.period_days} ngày.</p>
      <ul>{segments?.map(row => <li key={row.key}>
        Từ {row.starts_on} đến trước {row.ends_on}: {row.days}/{calculation.period_days} ngày,
        {' '}{row.quantity} × {money(row.rate_vnd)} × {row.days}/{calculation.period_days}.
      </li>)}</ul>
      <p>Thành tiền: {money(calculation.line_amount_vnd ?? calculation.amount_vnd)}. Các khoảng cùng đơn vị làm tròn được cộng trước khi làm tròn.</p>
      <p>Đơn vị làm tròn: {calculation.rounding_groups?.map(row => money(row.rounding_unit_vnd)).join(', ')}. Làm tròn đến đơn vị gần nhất; phần đúng nửa đơn vị được làm tròn lên.</p>
    </>}
  </details>;
}

import React from 'react';
import { State, usePortalCommand } from './PortalPanels';

export function NotificationAcknowledgement({ client, row, onDone }) {
  const command = usePortalCommand(client, onDone);
  return <div><State state={command} />{row.acknowledged_at ? <p>Đã xác nhận tiếp nhận.</p> : <button type="button" className="button-secondary" disabled={command.busy} onClick={() => command.run(`/control/notifications/${row.id}/ack`, {})}>Xác nhận tiếp nhận</button>}</div>;
}

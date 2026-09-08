import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

export function Dialog({ open, onClose, title, children, busy = false, wide = false, initialFocusId }) {
  const ref = useRef(null);
  const titleId = useId();
  const containTab = event => {
    if (event.key !== 'Tab') return;
    const focusable = [...ref.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])')]
      .filter(element => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first) { event.preventDefault(); ref.current.focus(); return; }
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  useEffect(() => {
    const element = ref.current;
    const previous = document.activeElement;
    if (open && !element.open) element.showModal();
    if (open && initialFocusId) document.getElementById(initialFocusId)?.focus();
    if (!open && element.open) element.close();
    return () => {
      if (element.open) element.close();
      if (open && previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [open, initialFocusId]);
  return (
    <dialog ref={ref} aria-labelledby={titleId} aria-busy={busy || undefined} onKeyDown={containTab}
      className={`app-dialog ${wide ? 'app-dialog-wide' : ''}`}
      onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
      <div className="dialog-heading">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="icon-button" aria-label="Đóng hộp thoại" disabled={busy} onClick={onClose} autoFocus>
          <X size={19} aria-hidden="true" />
        </button>
      </div>
      {open && children}
    </dialog>
  );
}

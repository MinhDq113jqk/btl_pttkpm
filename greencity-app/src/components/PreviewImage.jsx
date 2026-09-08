import React, { useState } from 'react';
import { Image as ImageIcon } from 'lucide-react';

// Remote illustrations are optional; reserve their space even offline.
export function PreviewImage({ src, alt = '', className = '', ...props }) {
  const [state, setState] = useState({ src, status: 'loading' });
  const status = state.src === src ? state.status : 'loading';
  return <span className={`preview-image ${className}`} role={status === 'error' ? 'img' : undefined} aria-label={status === 'error' ? `${alt || 'Ảnh minh họa'} · Không tải được ảnh` : undefined}>
    {status !== 'loaded' && <span className="preview-image-placeholder" aria-hidden="true"><ImageIcon size={24} /></span>}
    <img {...props} src={src} alt={status === 'error' ? '' : alt} loading="lazy" onLoad={() => setState({ src, status: 'loaded' })} onError={() => setState({ src, status: 'error' })} style={{ opacity: status === 'loaded' ? 1 : 0 }} />
  </span>;
}

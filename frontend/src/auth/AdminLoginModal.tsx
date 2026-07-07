import { useState, type FormEvent } from 'react';
import { LockIcon } from './icons';
import { useAdminAuth } from './AdminAuthContext';
import './admin.css';

interface Props {
  open: boolean;
  onClose: () => void;
  errorMsg?: string;
}

/**
 * Admin login modal — paper aesthetic.
 * Calls login(token, remember) on submit; the parent decides when to show it.
 */
export default function AdminLoginModal({ open, onClose, errorMsg }: Props) {
  const { login } = useAdminAuth();
  const [token, setToken] = useState('');
  const [remember, setRemember] = useState(true);

  if (!open) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) return;
    login(trimmed, remember);
    setToken('');
    setRemember(true);
    onClose();
  };

  return (
    <div className="alm-overlay" onClick={onClose}>
      <form className="alm-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <div className="alm-header">
          <LockIcon className="alm-icon" />
          <span className="alm-title">管理员验证</span>
        </div>
        <p className="alm-subtitle">
          「公司深度分析」需要管理员权限。请输入 admin token 继续。
        </p>
        <input
          className="alm-input"
          type="password"
          placeholder="X-Admin-Token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoFocus
        />
        {errorMsg && <div className="alm-error">{errorMsg}</div>}
        <label className="alm-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          <span>记住我(永久保留在此浏览器)</span>
        </label>
        <div className="alm-actions">
          <button type="button" className="alm-btn alm-btn-ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="alm-btn" disabled={!token.trim()}>
            进入
          </button>
        </div>
      </form>
    </div>
  );
}

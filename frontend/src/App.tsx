import { useEffect, useState } from 'react';
import { LockIcon, UnlockIcon } from './auth/icons';
import ChainPage from './pages/ChainPage';
import DeepAnalysisPage from './pages/DeepAnalysisPage';
import { AdminAuthProvider, useAdminAuth } from './auth/AdminAuthContext';
import AdminLoginModal from './auth/AdminLoginModal';
import './nav.css';

type View = 'chain' | 'deep';

interface NavItem {
  key: View;
  label: string;
  locked: boolean; // true = requires admin
}

const NAV_ITEMS: NavItem[] = [
  { key: 'chain', label: '产业链知识库', locked: false },
  { key: 'deep', label: '公司深度分析', locked: true },
];

function AppInner() {
  const { isAdmin } = useAdminAuth();
  const [view, setView] = useState<View>('chain');
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginError, setLoginError] = useState('');

  const handleNavClick = (item: NavItem) => {
    if (item.locked && !isAdmin) {
      setLoginError(''); // fresh open, no stale error
      setLoginModalOpen(true);
      return;
    }
    setView(item.key);
  };

  // AdminAuthContext clears the token on 401; we watch isAdmin going
  // false while the user is on the 'deep' view, and bounce them back
  // to 'chain' + reopen the modal with an error.
  // Implemented as an effect on isAdmin.
  // (Doing this in AppInner keeps view/modal state local.)
  // Use a separate effect via useEffect:
  // (Import useEffect at the top — see step 2 if you forgot.)

  // Watch for unexpected 401 (axios interceptor cleared the token while
  // the user is sitting on the protected page). Reopen modal + show error.
  useEffect(() => {
    if (!isAdmin && view === 'deep') {
      setLoginError('管理员 token 已失效,请重新输入。');
      setLoginModalOpen(true);
    }
  }, [isAdmin, view]);

  return (
    <div className="app-root">
      <nav className="app-nav">
        <span className="app-nav-brand">InvestLens</span>
        <div className="app-nav-items">
          {NAV_ITEMS.map((item) => {
            const locked = item.locked && !isAdmin;
            const unlocked = item.locked && isAdmin;
            return (
              <button
                key={item.key}
                className={`app-nav-item ${view === item.key ? 'active' : ''}`}
                onClick={() => handleNavClick(item)}
              >
                {locked && <LockIcon style={{ marginRight: 6 }} />}
                {unlocked && <UnlockIcon style={{ marginRight: 6 }} />}
                {item.label}
              </button>
            );
          })}
        </div>
      </nav>
      <main className="app-main">
        {view === 'chain' && <ChainPage />}
        {view === 'deep' && isAdmin && <DeepAnalysisPage onExit={() => setView('chain')} />}
        {view === 'deep' && !isAdmin && (
          <div style={{ padding: 32, color: 'var(--ink-soft)' }}>
            此页面需要管理员权限。
          </div>
        )}
      </main>
      <AdminLoginModal
        open={loginModalOpen}
        onClose={() => setLoginModalOpen(false)}
        errorMsg={loginError}
      />
    </div>
  );
}

export default function App() {
  return (
    <AdminAuthProvider>
      <AppInner />
    </AdminAuthProvider>
  );
}

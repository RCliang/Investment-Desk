import { useState } from 'react';
import ChainPage from './pages/ChainPage';
import DeepAnalysisPage from './pages/DeepAnalysisPage';
import './nav.css';

type View = 'chain' | 'deep';

const NAV_ITEMS: { key: View; label: string }[] = [
  { key: 'chain', label: '产业链知识库' },
  { key: 'deep', label: '个股深度分析' },
];

/**
 * 顶层 view switcher。无 react-router，只用 useState 切换。
 * 每个视图自管主题：ChainPage 沿用 .chainkb-root 纸质主题；
 * DeepAnalysisPage 使用 GitHub-inspired 暗色主题。
 */
export default function App() {
  const [view, setView] = useState<View>('chain');

  return (
    <div className="app-root">
      <nav className="app-nav">
        <span className="app-nav-brand">InvestLens</span>
        <div className="app-nav-items">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`app-nav-item ${view === item.key ? 'active' : ''}`}
              onClick={() => setView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </nav>
      <main className="app-main">
        {view === 'chain' && <ChainPage />}
        {view === 'deep' && <DeepAnalysisPage />}
      </main>
    </div>
  );
}

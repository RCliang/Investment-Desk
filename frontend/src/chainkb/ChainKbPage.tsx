import { useCallback, useState } from 'react';
import './chainkb.css';
import OverviewScreen from './OverviewScreen';
import LayerScreen from './LayerScreen';
import FinanceScreen from './FinanceScreen';
import DataFreshness from './components/DataFreshness';
import { useFreshness } from './hooks/useChainKb';

type TabKey = 'overview' | 'layers' | 'finance';

interface TabDef {
  key: TabKey;
  label: string;
  disabled?: boolean;
}

const TABS: TabDef[] = [
  { key: 'overview', label: '00 · 总览' },
  { key: 'layers', label: '01 · 产业链层级' },
  // 02 · 公司对比 — deferred (compare-basket UX)
  { key: 'finance', label: '03 · 财务拆解' },
  // 04 · 风险标记 — deferred (risk inference layer)
];

export default function ChainKbPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const freshness = useFreshness();

  // Cross-tab drill-down state
  const [drilledGroupId, setDrilledGroupId] = useState<string | null>(null);
  const [drilledTicker, setDrilledTicker] = useState<string | null>(null);

  const handleSelectSubIndustry = useCallback((groupId: string) => {
    setDrilledGroupId(groupId);
    setActiveTab('layers');
  }, []);

  const handleSelectTicker = useCallback((ticker: string) => {
    setDrilledTicker(ticker);
    setActiveTab('finance');
  }, []);

  const handleResetGroupId = useCallback(() => {
    // Clear the drill-down trigger after LayerScreen has consumed it
    // so a subsequent click on the same group_id still registers.
    setDrilledGroupId(null);
  }, []);

  const handleResetTicker = useCallback(() => {
    setDrilledTicker(null);
  }, []);

  return (
    <div className="chainkb-root">
      <div className="wrap">
        {/* Header */}
        <header className="header">
          <div>
            <div className="header-left">
              <h1>产业链知识库</h1>
              <span className="version-tag">CHAINKB · v1</span>
            </div>
            <div className="subtitle">投资研究 · 五层产业链拆解视图</div>
          </div>
          <div className="dateline">
            <DataFreshness freshness={freshness} />
          </div>
        </header>

        {/* Tab strip */}
        <nav className="tabs">
          {TABS.map((tab) => {
            const isActive = tab.key === activeTab;
            return (
              <div
                key={tab.key}
                className={`tab ${isActive ? 'active' : ''}`}
                onClick={() => !tab.disabled && setActiveTab(tab.key)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if ((e.key === 'Enter' || e.key === ' ') && !tab.disabled) {
                    e.preventDefault();
                    setActiveTab(tab.key);
                  }
                }}
                style={tab.disabled ? { opacity: 0.4, cursor: 'not-allowed' } : undefined}
              >
                {isActive && <span className="tab-highlight" />}
                <span className={`tab-check ${isActive ? 'checked' : ''}`} />
                <span>{tab.label}</span>
              </div>
            );
          })}
        </nav>

        {/* Active screen */}
        {activeTab === 'overview' && (
          <OverviewScreen onSelectSubIndustry={handleSelectSubIndustry} />
        )}
        {activeTab === 'layers' && (
          <LayerScreen
            initialGroupId={drilledGroupId}
            onSelectTicker={handleSelectTicker}
            onResetGroupId={handleResetGroupId}
          />
        )}
        {activeTab === 'finance' && (
          <FinanceScreen
            initialTicker={drilledTicker}
            onResetTicker={handleResetTicker}
          />
        )}
      </div>
    </div>
  );
}

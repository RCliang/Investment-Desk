import { useState } from 'react';
import { Input, Button, Card, Row, Col, Descriptions, Table, Tag, Spin, Typography, message } from 'antd';
import { SearchOutlined, LineChartOutlined, DollarOutlined, FundOutlined, FileTextOutlined, AppstoreOutlined, SwapOutlined } from '@ant-design/icons';
import { getStockQuote, getStockHist, getStockFinancial, getStockReports, getStockBlocks, getStockFundFlow } from '../services/api';

const { Title } = Typography;

type TabKey = 'quote' | 'hist' | 'financial' | 'reports' | 'blocks' | 'fundflow';

interface TabDef {
  key: TabKey;
  label: string;
  icon: React.ReactNode;
}

const tabs: TabDef[] = [
  { key: 'quote', label: '实时报价', icon: <DollarOutlined /> },
  { key: 'hist', label: '历史K线', icon: <LineChartOutlined /> },
  { key: 'financial', label: '财务指标', icon: <FundOutlined /> },
  { key: 'reports', label: '研报', icon: <FileTextOutlined /> },
  { key: 'blocks', label: '概念板块', icon: <AppstoreOutlined /> },
  { key: 'fundflow', label: '资金流向', icon: <SwapOutlined /> },
];

function buildColumns(data: Record<string, unknown>[]): { title: string; dataIndex: string; key: string }[] {
  if (!data || data.length === 0) return [];
  const keys = Object.keys(data[0]);
  return keys.map((k) => ({ title: k, dataIndex: k, key: k, ellipsis: true }));
}

export default function DataPage() {
  const [code, setCode] = useState('');
  const [activeTab, setActiveTab] = useState<TabKey>('quote');
  const [loading, setLoading] = useState(false);
  const [quoteData, setQuoteData] = useState<Record<string, unknown> | null>(null);
  const [tableData, setTableData] = useState<Record<string, unknown>[]>([]);
  const [reportsData, setReportsData] = useState<Record<string, unknown>[]>([]);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!code.trim()) {
      message.warning('请输入股票代码');
      return;
    }
    setSearched(false);
    setLoading(true);
    setQuoteData(null);
    setTableData([]);
    setReportsData([]);
    try {
      if (activeTab === 'quote') {
        const data = await getStockQuote(code);
        setQuoteData(data as Record<string, unknown>);
      } else if (activeTab === 'hist') {
        const data = await getStockHist(code);
        setTableData(Array.isArray(data) ? data : []);
      } else if (activeTab === 'financial') {
        const data = await getStockFinancial(code);
        setTableData(Array.isArray(data) ? data : []);
      } else if (activeTab === 'reports') {
        const data = await getStockReports(code);
        setReportsData(Array.isArray(data) ? data : []);
      } else if (activeTab === 'blocks') {
        const data = await getStockBlocks(code);
        setTableData(Array.isArray(data) ? data : []);
      } else if (activeTab === 'fundflow') {
        const data = await getStockFundFlow(code);
        setTableData(Array.isArray(data) ? data : []);
      }
      setSearched(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '查询失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (key: TabKey) => {
    setActiveTab(key);
    setSearched(false);
    setQuoteData(null);
    setTableData([]);
    setReportsData([]);
  };

  const renderContent = () => {
    if (loading) {
      return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="查询中..." /></div>;
    }
    if (!searched) {
      return <div style={{ textAlign: 'center', padding: 60, color: '#6e7681' }}>请输入股票代码并点击查询</div>;
    }

    switch (activeTab) {
      case 'quote':
        if (!quoteData) return <div style={{ textAlign: 'center', padding: 40, color: '#6e7681' }}>暂无数据</div>;
        return (
          <Descriptions bordered size="small" column={2} style={{ background: '#1c2330' }}>
            {Object.entries(quoteData).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {typeof v === 'number' && String(v).includes('-') ? (
                  <span style={{ color: '#f85149' }}>{String(v)}</span>
                ) : (
                  String(v ?? '-')
                )}
              </Descriptions.Item>
            ))}
          </Descriptions>
        );
      case 'reports':
        return (
          <Table
            dataSource={reportsData.map((r, i) => ({ ...r, key: i }))}
            columns={[
              { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
              { title: '机构', dataIndex: 'org', key: 'org', width: 150 },
              { title: '评级', dataIndex: 'rating', key: 'rating', width: 80, render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
              { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
            ]}
            size="small"
            pagination={{ pageSize: 20 }}
          />
        );
      default:
        return (
          <Table
            dataSource={tableData.map((r, i) => ({ ...r, key: i }))}
            columns={buildColumns(tableData)}
            size="small"
            pagination={{ pageSize: 20 }}
            scroll={{ x: 'max-content' }}
          />
        );
    }
  };

  return (
    <div>
      <Title level={4} style={{ color: '#e6edf3', marginTop: 0 }}>数据查询</Title>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="输入股票代码，如 600519"
          style={{ maxWidth: 240 }}
          onPressEnter={handleSearch}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          查询
        </Button>
      </div>

      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        {tabs.map((tab) => (
          <Col key={tab.key} span={4}>
            <Card
              size="small"
              hoverable
              onClick={() => handleTabChange(tab.key)}
              style={{
                background: activeTab === tab.key ? '#1c2330' : '#0d1117',
                border: activeTab === tab.key ? '1px solid #1f6feb' : '1px solid rgba(48,54,61,0.9)',
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 20, marginBottom: 4 }}>{tab.icon}</div>
              <div style={{ fontSize: 12, color: activeTab === tab.key ? '#e6edf3' : '#8b949e' }}>{tab.label}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card size="small" style={{ background: '#1c2330' }}>
        {renderContent()}
      </Card>
    </div>
  );
}

import { useState } from 'react';
import { Input, Button, Card, Row, Col, Table, Tag, Spin, Typography, message } from 'antd';
import { ThunderboltOutlined, RightOutlined } from '@ant-design/icons';
import { analyzeChain } from '../services/api';

const { Text } = Typography;

const oppColors: Record<string, string> = { high: 'green', mid: 'orange', low: 'default' };
const oppLabels: Record<string, string> = { high: '高', mid: '中', low: '低' };
const colColors: Record<string, string> = { upstream: '#a371f7', midstream: '#388bfd', downstream: '#3fb950' };
const colTitles: Record<string, string> = { upstream: '上游原材料', midstream: '中游制造', downstream: '下游应用' };

interface ChainItem {
  name: string;
  opp_level: string;
  summary: string;
}

interface ChainSummary {
  market_size: string;
  growth_rate: string;
  overall_rating: string;
  opportunity_count: number;
  high_confidence_count: number;
}

interface ChainResult {
  summary: ChainSummary;
  upstream: ChainItem[];
  midstream: ChainItem[];
  downstream: ChainItem[];
}

function ChainColumn({ stage, items }: { stage: string; items: ChainItem[] }) {
  return (
    <Card
      size="small"
      title={<Text style={{ color: colColors[stage] }}>{colTitles[stage]}</Text>}
      style={{ flex: 1 }}
    >
      {items.map((item, i) => (
        <div key={i} style={{
          padding: '6px 8px', marginBottom: 3, borderRadius: 4,
          background: '#21262d', cursor: 'pointer', fontSize: 12,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{item.name}</span>
          <Tag color={oppColors[item.opp_level]} style={{ margin: 0 }}>
            {oppLabels[item.opp_level]}
          </Tag>
        </div>
      ))}
    </Card>
  );
}

export default function ChainPage() {
  const [industry, setIndustry] = useState('新能源汽车');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ChainResult | null>(null);

  const handleAnalyze = async () => {
    if (!industry.trim()) return;
    setLoading(true);
    try {
      const result = await analyzeChain(industry.trim());
      setData(result);
    } catch {
      message.error('分析失败，请检查网络连接');
    } finally {
      setLoading(false);
    }
  };

  const allItems = [
    ...(data?.upstream || []).map(i => ({ ...i, stage: 'upstream' })),
    ...(data?.midstream || []).map(i => ({ ...i, stage: 'midstream' })),
    ...(data?.downstream || []).map(i => ({ ...i, stage: 'downstream' })),
  ].sort((a, b) => {
    const order = { high: 0, mid: 1, low: 2 };
    return (order[a.opp_level] || 2) - (order[b.opp_level] || 2);
  });

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Input
          value={industry}
          onChange={e => setIndustry(e.target.value)}
          placeholder="输入产业名称…"
          style={{ width: 280 }}
          onPressEnter={handleAnalyze}
        />
        <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleAnalyze} loading={loading}>
          启动 AI 分析
        </Button>
      </div>

      <Spin spinning={loading}>
        {data && (
          <>
            <Row gutter={8} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small">
                  <Text type="secondary" style={{ fontSize: 11 }}>产业规模</Text><br />
                  <Text strong style={{ fontSize: 20, color: '#388bfd' }}>{data.summary.market_size}</Text><br />
                  <Text type="secondary" style={{ fontSize: 11 }}>同比 {data.summary.growth_rate}</Text>
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Text type="secondary" style={{ fontSize: 11 }}>识别机会数</Text><br />
                  <Text strong style={{ fontSize: 20, color: '#3fb950' }}>{data.summary.opportunity_count}</Text><br />
                  <Text type="secondary" style={{ fontSize: 11 }}>高确信度 {data.summary.high_confidence_count} 个</Text>
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Text type="secondary" style={{ fontSize: 11 }}>综合评级</Text><br />
                  <Text strong style={{ fontSize: 20, color: '#d29922' }}>{data.summary.overall_rating}</Text>
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Text type="secondary" style={{ fontSize: 11 }}>数据更新</Text><br />
                  <Text style={{ fontSize: 13 }}>{new Date().toLocaleString('zh-CN')}</Text>
                </Card>
              </Col>
            </Row>

            <Text style={{ fontSize: 11, color: '#6e7681', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              产业链全景 — {industry}
            </Text>

            <Row gutter={8} style={{ marginTop: 8, marginBottom: 16 }}>
              {(['upstream', 'midstream', 'downstream'] as const).map((stage, idx) => (
                <Col key={stage} style={{ display: 'flex', alignItems: 'center' }}>
                  {idx > 0 && <RightOutlined style={{ color: '#6e7681', margin: '0 4px' }} />}
                  <ChainColumn stage={stage} items={data[stage]} />
                </Col>
              ))}
            </Row>

            <Text style={{ fontSize: 11, color: '#6e7681' }}>机会优先级排序</Text>
            <Table
              size="small"
              dataSource={allItems}
              rowKey={(_, i) => String(i)}
              pagination={false}
              columns={[
                { title: '环节', dataIndex: 'name', render: t => <Text strong>{t}</Text> },
                {
                  title: '阶段', dataIndex: 'stage',
                  render: t => <Tag color={colColors[t]}>{colTitles[t]}</Tag>,
                },
                {
                  title: '机会评级', dataIndex: 'opp_level',
                  render: t => <Tag color={oppColors[t]}>{oppLabels[t]}</Tag>,
                },
                { title: '说明', dataIndex: 'summary', width: '40%' },
              ]}
            />
          </>
        )}
      </Spin>
    </div>
  );
}

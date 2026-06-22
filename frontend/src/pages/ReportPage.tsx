import { useState, useEffect, useCallback } from 'react';
import { Input, Button, List, Spin, Typography, Card, message } from 'antd';
import { FileAddOutlined, FileTextOutlined } from '@ant-design/icons';
import { generateReport, listReports, getReport } from '../services/api';
import MarkdownRenderer from '../components/MarkdownRenderer';

const { Title, Text } = Typography;

interface ReportItem {
  id: number;
  industry: string;
  created_at: string;
}

export default function ReportPage() {
  const [industry, setIndustry] = useState('');
  const [generating, setGenerating] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [history, setHistory] = useState<ReportItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedReport, setSelectedReport] = useState<string>('');
  const [viewContent, setViewContent] = useState('');

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const data = await listReports();
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      // ignore
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleGenerate = async () => {
    if (!industry.trim()) {
      message.warning('请输入行业名称');
      return;
    }
    setGenerating(true);
    setStreamContent('');
    setSelectedReport('');
    setViewContent('');

    try {
      await generateReport(industry, (chunk) => {
        setStreamContent((prev) => prev + chunk);
      });
      message.success('报告生成完成');
      loadHistory();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '生成失败';
      message.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const handleViewReport = async (item: ReportItem) => {
    setSelectedReport(`报告 #${item.id}`);
    setStreamContent('');
    setViewContent('');
    try {
      const data = await getReport(item.id);
      setViewContent((data as Record<string, unknown>).content as string || JSON.stringify(data));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    }
  };

  const displayContent = selectedReport ? viewContent : streamContent;

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 140px)' }}>
      {/* Left Sidebar */}
      <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Card size="small" style={{ background: '#1c2330' }}>
          <Input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="输入行业名称"
            style={{ marginBottom: 8 }}
            onPressEnter={handleGenerate}
          />
          <Button
            type="primary"
            icon={<FileAddOutlined />}
            loading={generating}
            onClick={handleGenerate}
            block
          >
            生成投资报告
          </Button>
        </Card>

        <Card
          size="small"
          title={<Text style={{ color: '#e6edf3', fontSize: 13 }}>历史报告</Text>}
          style={{ background: '#1c2330', flex: 1, overflow: 'auto' }}
          bodyStyle={{ padding: 0 }}
        >
          {loadingHistory ? (
            <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
          ) : history.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#6e7681' }}>暂无报告</div>
          ) : (
            <List
              size="small"
              dataSource={history}
              renderItem={(item) => (
                <List.Item
                  onClick={() => handleViewReport(item)}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 12px',
                    background: selectedReport === `报告 #${item.id}` ? 'rgba(31,111,235,0.15)' : 'transparent',
                    borderLeft: selectedReport === `报告 #${item.id}` ? '2px solid #1f6feb' : '2px solid transparent',
                  }}
                >
                  <div>
                    <div style={{ color: '#e6edf3', fontSize: 13 }}>
                      <FileTextOutlined style={{ marginRight: 6 }} />
                      {item.industry}
                    </div>
                    <div style={{ color: '#6e7681', fontSize: 11 }}>{item.created_at}</div>
                  </div>
                </List.Item>
              )}
            />
          )}
        </Card>
      </div>

      {/* Right Content */}
      <Card
        size="small"
        style={{ background: '#1c2330', flex: 1, overflow: 'auto' }}
        bodyStyle={{ padding: 16, height: '100%', overflow: 'auto' }}
      >
        {generating && !streamContent && (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="AI 正在生成报告..." />
          </div>
        )}
        {generating && streamContent && (
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: '#8b949e', fontSize: 12 }}>正在生成中...</span>
          </div>
        )}
        {selectedReport && (
          <Title level={5} style={{ color: '#e6edf3', marginTop: 0, marginBottom: 12 }}>{selectedReport}</Title>
        )}
        {displayContent ? (
          <MarkdownRenderer content={displayContent} />
        ) : !generating ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#6e7681' }}>
            选择左侧历史报告或生成新报告
          </div>
        ) : null}
      </Card>
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import { Button, Table, Modal, Form, Input, InputNumber, Select, Popconfirm, Typography, Tag, Space, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { createPlan, listPlans, updatePlan, deletePlan } from '../services/api';

const { Title } = Typography;

interface PlanRecord {
  id: number;
  stock_code: string;
  stock_name: string;
  direction: string;
  position_ratio: number;
  target_price?: number;
  stop_loss_price?: number;
  status: string;
  reason?: string;
  created_at: string;
}

const statusOptions = [
  { value: '待执行', label: '待执行' },
  { value: '执行中', label: '执行中' },
  { value: '已平仓', label: '已平仓' },
  { value: '已止损', label: '已止损' },
];

export default function PlanPage() {
  const [plans, setPlans] = useState<PlanRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPlans();
      setPlans(Array.isArray(data) ? data : []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const handleCreate = () => {
    setEditingId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: PlanRecord) => {
    setEditingId(record.id);
    form.setFieldsValue({
      stock_code: record.stock_code,
      stock_name: record.stock_name,
      direction: record.direction,
      position_ratio: record.position_ratio,
      target_price: record.target_price,
      stop_loss_price: record.stop_loss_price,
      reason: record.reason,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingId !== null) {
        await updatePlan(editingId, values);
        message.success('更新成功');
      } else {
        await createPlan(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      form.resetFields();
      loadPlans();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // form validation error
      const msg = err instanceof Error ? err.message : '操作失败';
      message.error(msg);
    }
  };

  const handleStatusChange = async (id: number, status: string) => {
    try {
      await updatePlan(id, { status });
      loadPlans();
    } catch {
      message.error('状态更新失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deletePlan(id);
      message.success('删除成功');
      loadPlans();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    {
      title: '代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 100,
      render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span>,
    },
    {
      title: '名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      width: 80,
      render: (v: string) => (
        <Tag color={v === '买入' ? 'green' : 'red'}>{v}</Tag>
      ),
    },
    {
      title: '仓位 %',
      dataIndex: 'position_ratio',
      key: 'position_ratio',
      width: 80,
      render: (v: number) => `${v}%`,
    },
    {
      title: '目标价',
      dataIndex: 'target_price',
      key: 'target_price',
      width: 90,
      render: (v: number | undefined) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: '止损价',
      dataIndex: 'stop_loss_price',
      key: 'stop_loss_price',
      width: 90,
      render: (v: number | undefined) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (v: string, record: PlanRecord) => (
        <Select
          value={v}
          size="small"
          style={{ width: 100 }}
          onChange={(val) => handleStatusChange(record.id, val)}
          options={statusOptions}
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: PlanRecord) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除此计划？" onConfirm={() => handleDelete(record.id)} okText="删除" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ color: '#e6edf3', margin: 0 }}>投资计划</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新建计划
        </Button>
      </div>

      <Table
        dataSource={plans.map((p) => ({ ...p, key: p.id }))}
        columns={columns}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1000 }}
      />

      <Modal
        title={editingId !== null ? '编辑投资计划' : '新建投资计划'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="stock_code" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
            <Input placeholder="如 600519" />
          </Form.Item>
          <Form.Item name="stock_name" label="股票名称" rules={[{ required: true, message: '请输入股票名称' }]}>
            <Input placeholder="如 贵州茅台" />
          </Form.Item>
          <Form.Item name="direction" label="方向" rules={[{ required: true, message: '请选择方向' }]}>
            <Select options={[{ value: '买入', label: '买入' }, { value: '卖出', label: '卖出' }]} />
          </Form.Item>
          <Form.Item name="position_ratio" label="仓位比例 (%)" rules={[{ required: true, message: '请输入仓位比例' }]}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="target_price" label="目标价">
            <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="stop_loss_price" label="止损价">
            <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="reason" label="理由">
            <Input.TextArea rows={3} placeholder="投资理由..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

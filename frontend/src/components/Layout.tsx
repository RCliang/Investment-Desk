import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  ApartmentOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  ScheduleOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/chain', icon: <ApartmentOutlined />, label: '产业链图谱' },
  { key: '/data', icon: <DatabaseOutlined />, label: '数据查询' },
  { key: '/report', icon: <FileTextOutlined />, label: '投资报告' },
  { key: '/plan', icon: <ScheduleOutlined />, label: '投资计划' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh', background: '#0d1117' }}>
      <Header style={{ background: '#161b22', borderBottom: '1px solid rgba(48,54,61,0.9)', display: 'flex', alignItems: 'center', padding: '0 16px' }}>
        <Typography.Text strong style={{ color: '#388bfd', fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          InvestLens
        </Typography.Text>
        <Typography.Text style={{ color: '#6e7681', fontSize: 11, marginLeft: 8 }}>
          v0.1
        </Typography.Text>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#161b22', borderRight: '1px solid rgba(48,54,61,0.9)' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ background: 'transparent', border: 'none' }}
          />
        </Sider>
        <Content style={{ padding: 16, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

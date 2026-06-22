import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import Layout from './components/Layout';
import ChainPage from './pages/ChainPage';
import DataPage from './pages/DataPage';
import ReportPage from './pages/ReportPage';
import PlanPage from './pages/PlanPage';

export default function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1f6feb',
          colorBgContainer: '#161b22',
          colorBgElevated: '#1c2330',
          colorBorder: 'rgba(48,54,61,0.9)',
          colorText: '#e6edf3',
          colorTextSecondary: '#8b949e',
          borderRadius: 6,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Navigate to="/chain" replace />} />
            <Route path="/chain" element={<ChainPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/plan" element={<PlanPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

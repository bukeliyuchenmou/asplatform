import { useState, useEffect, Suspense, lazy } from 'react';
import { useNavigate, useLocation, Routes, Route, Navigate } from 'react-router-dom';
import { Layout, Menu, Button, Typography, Spin, List, Result, Space } from 'antd';
import {
  ExperimentOutlined, EditOutlined, BookOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, LogoutOutlined,
  FileTextOutlined, PlusOutlined, ToolOutlined,
  ShoppingCartOutlined, VideoCameraOutlined,
} from '@ant-design/icons';
import ServiceTokenGuard from '../components/common/ServiceTokenGuard';
import TokenQuotaBar from '../components/common/TokenQuotaBar';
import { useServiceToken } from '../hooks/useServiceToken';
import { listProjects } from '../services/thesisApi';
import type { ThesisProject } from '../types/thesis';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const BioAnalysisWorkbench = lazy(() => import('../pages/bio/BioAnalysisWorkbench'));
const AIWritingWorkbench = lazy(() => import('../pages/writing/AIWritingWorkbench'));
const LiteratureCompareWorkbench = lazy(() => import('../pages/literature/LiteratureCompareWorkbench'));
const AITools = lazy(() => import('../pages/AITools'));
const VideoSearchExamplePage = lazy(() => import('../pages/VideoSearchExamplePage'));
const PaymentOrdersPage = lazy(() => import('../pages/PaymentOrdersPage'));

function PageFallback() {
  return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 200 }}><Spin /></div>;
}

const menuItems = [
  { key: 'bio', icon: <ExperimentOutlined />, label: '生信分析', path: '/frontend/bio' },
  { key: 'writing', icon: <EditOutlined />, label: 'AI 写作', path: '/frontend/writing' },
  { key: 'ai-tools', icon: <ToolOutlined />, label: 'AI 工具', path: '/frontend/ai-tools' },
  { key: 'video-search', icon: <VideoCameraOutlined />, label: '调用视频', path: '/frontend/video-search' },
  { key: 'lit-compare', icon: <BookOutlined />, label: '文献分析', path: '/frontend/lit-compare' },
  { key: 'orders', icon: <ShoppingCartOutlined />, label: '订单记录', path: '/frontend/orders' },
];

function getKey(pathname: string) {
  for (const m of menuItems) if (pathname.startsWith(m.path)) return m.key;
  return 'bio';
}

function FrontendLayoutInner() {
  const navigate = useNavigate();
  const location = useLocation();
  const { serviceToken, tokenInfo, clearToken } = useServiceToken();
  const [collapsed, setCollapsed] = useState(false);
  const [projects, setProjects] = useState<ThesisProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);

  const isWriting = location.pathname.startsWith('/frontend/writing');
  const canUseProFeature = tokenInfo?.source !== 'oauth' || tokenInfo?.entitlement_level === 'pro';

  // Load projects
  const loadProjectList = async () => {
    if (!serviceToken) return;
    setProjectsLoading(true);
    try {
      const data = await listProjects(serviceToken);
      setProjects(data);
    } catch { /* silent */ }
    finally { setProjectsLoading(false); }
  };

  useEffect(() => {
    if (isWriting && serviceToken) loadProjectList();
  }, [isWriting, serviceToken]);

  const handleMenuClick = (info: { key: string }) => {
    const item = menuItems.find(m => m.key === info.key);
    if (item) navigate(item.path);
  };

  const handleSelectProject = (p: ThesisProject) => {
    setSelectedProjectId(p.id);
  };

  const handleNewProject = () => {
    setSelectedProjectId(null);
  };

  const renderProRequired = (featureName: string) => (
    <Result
      status="warning"
      title={`${featureName}需要高级会员`}
      subTitle={`当前账号套餐暂未开放${featureName}，请升级到高级会员后继续使用。`}
      extra={
        <Space>
          <Button onClick={() => navigate('/frontend/orders')}>查看订单</Button>
          <Button type="primary" onClick={() => navigate('/payment/upgrade')}>
            升级到高级会员
          </Button>
        </Space>
      }
    />
  );

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible collapsed={collapsed} onCollapse={setCollapsed}
        width={220}
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 10 }}
        theme="dark"
      >
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          {collapsed
            ? <ExperimentOutlined style={{ fontSize: 22, color: '#fff' }} />
            : <Text strong style={{ color: '#fff', fontSize: 16 }}>学术辅助平台</Text>}
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[getKey(location.pathname)]}
          onClick={handleMenuClick}
          items={menuItems.map(m => ({ key: m.key, icon: m.icon, label: m.label }))}
          style={{ marginTop: 8 }}
        />

        {/* Project list — only on writing route, not collapsed */}
        {isWriting && !collapsed && (
          <div className={"chat-container"} style={{ marginTop: 4, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px 4px' }}>
              <Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>项目列表</Text>
              <Button type="text" size="small" icon={<PlusOutlined />}
                style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}
                onClick={handleNewProject}>新建</Button>
            </div>
            {projectsLoading ? (
              <div style={{ textAlign: 'center', padding: 12 }}><Spin size="small" /></div>
            ) : projects.length === 0 ? (
              <Text style={{ color: 'rgba(255,255,255,0.25)', fontSize: 11, display: 'block', padding: '8px 16px' }}>暂无项目</Text>
            ) : (
              <List
                size="small"
                dataSource={projects}
                style={{ maxHeight: 'calc(100vh - 360px)', overflowY: 'auto' }}
                renderItem={(p) => (
                  <div
                    onClick={() => { setSelectedProjectId(p.id); }}
                    style={{
                      padding: '6px 16px', cursor: 'pointer',
                      background: selectedProjectId === p.id ? 'rgba(255,255,255,0.12)' : 'transparent',
                      borderLeft: selectedProjectId === p.id ? '3px solid #1890ff' : '3px solid transparent',
                      transition: 'background 0.2s',
                    }}
                  >
                    <Text style={{
                      color: selectedProjectId === p.id ? '#fff' : 'rgba(255,255,255,0.65)',
                      fontSize: 12,
                    }} ellipsis={{ tooltip: p.title }}>
                      <FileTextOutlined style={{ marginRight: 6, fontSize: 10 }} />
                      {p.title}
                    </Text>
                  </div>
                )}
              />
            )}
          </div>
        )}
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>
        <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#fff', borderBottom: '1px solid #f0f0f0', padding: '0 24px', height: 64, position: 'sticky', top: 0, zIndex: 9 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)} style={{ fontSize: 16, width: 40, height: 40 }} />
            <TokenQuotaBar total={tokenInfo?.ai_quota ?? 0} used={tokenInfo?.used_quota ?? 0} />
            <Button
              type="primary"
              icon={<ShoppingCartOutlined />}
              onClick={() => navigate('/payment/upgrade')}
            >
              升级产品
            </Button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Button type="text" icon={<LogoutOutlined />} onClick={() => { clearToken(); navigate('/'); }} danger>退出</Button>
          </div>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="bio" element={
                canUseProFeature ? (
                  <BioAnalysisWorkbench />
                ) : (
                  renderProRequired('生信分析')
                )
              } />
              <Route path="writing" element={
                <AIWritingWorkbench
                  projects={projects}
                  selectedProjectId={selectedProjectId}
                  onProjectSelect={handleSelectProject}
                  onProjectNew={handleNewProject}
                  onProjectsRefresh={loadProjectList}
                  onProjectDelete={(id) => {
                    setProjects(prev => prev.filter(p => p.id !== id));
                    if (selectedProjectId === id) setSelectedProjectId(null);
                  }}
                />
              } />
              <Route path="ai-tools" element={<AITools />} />
              <Route path="video-search" element={
                canUseProFeature ? (
                  <VideoSearchExamplePage />
                ) : (
                  renderProRequired('调用视频')
                )
              } />
              <Route path="lit-compare" element={<LiteratureCompareWorkbench />} />
              <Route path="orders" element={<PaymentOrdersPage />} />
              <Route path="/" element={<Navigate to="bio" replace />} />
              <Route path="*" element={<Navigate to="bio" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function FrontendLayout() {
  return <ServiceTokenGuard><FrontendLayoutInner /></ServiceTokenGuard>;
}

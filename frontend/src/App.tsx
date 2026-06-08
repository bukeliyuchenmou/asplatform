import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import { ServiceTokenProvider } from './contexts/ServiceTokenContext';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { LoadingSpinner } from './components/common/LoadingSpinner';
import './styles/variables.css';

// ---------------------------------------------------------------------------
// Lazy-loaded pages & layouts
// ---------------------------------------------------------------------------
const LandingPage = lazy(() => import('./pages/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const AdminLayout = lazy(() => import('./layouts/AdminLayout'));
const FrontendLayout = lazy(() => import('./layouts/FrontendLayout'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const OAuthCallbackPage = lazy(() => import('./pages/OAuthCallbackPage'));
const PaymentReturnPage = lazy(() => import('./pages/PaymentReturnPage'));
const PaymentPurchasePage = lazy(() => import('./pages/PaymentPurchasePage'));
const PaymentUpgradePage = lazy(() => import('./pages/PaymentUpgradePage'));

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1a1a2e',
        },
      }}
    >
      <ErrorBoundary>
        <AuthProvider>
          <ServiceTokenProvider>
            <BrowserRouter>
              <Suspense fallback={<LoadingSpinner tip="页面加载中..." />}>
                <Routes>
                  <Route path="/" element={<LandingPage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/oauth/callback" element={<OAuthCallbackPage />} />
                  <Route path="/payment/return" element={<PaymentReturnPage />} />
                  <Route path="/payment/purchase" element={<PaymentPurchasePage />} />
                  <Route path="/payment/upgrade" element={<PaymentUpgradePage />} />
                  <Route path="/admin/*" element={<AdminLayout />} />
                  <Route path="/frontend/*" element={<FrontendLayout />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </ServiceTokenProvider>
        </AuthProvider>
      </ErrorBoundary>
    </ConfigProvider>
  );
}

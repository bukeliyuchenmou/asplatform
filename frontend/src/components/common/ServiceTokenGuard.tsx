import { useState, type ReactNode } from 'react';
import { Card, Button, Spin, Result, Space, Typography } from 'antd';
import { LoginOutlined } from '@ant-design/icons';
import { useServiceToken } from '../../hooks/useServiceToken';
import { authApi } from '../../services/authApi';
import { getOAuthOpenid, getOAuthUserToken } from '../../utils/oauthSession';

const { Text, Title } = Typography;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
export interface ServiceTokenGuardProps {
  children: ReactNode;
}

// ---------------------------------------------------------------------------
// ServiceTokenGuard — full-page account authorization component
//
// Three states:
//   1. No token       → full-page overlay with account authorization button
//   2. Verifying      → centered Spin
//   3. Valid          → renders children
//   4. Invalid        → error Result with account login / purchase options
// ---------------------------------------------------------------------------
export function ServiceTokenGuard({ children }: ServiceTokenGuardProps) {
  const { serviceToken, tokenInfo, isValid, isVerifying, clearToken } =
    useServiceToken();

  const [localError, setLocalError] = useState<string | null>(null);
  const [isOAuthStarting, setIsOAuthStarting] = useState<boolean>(false);
  const hasOAuthSession = Boolean(getOAuthOpenid() && getOAuthUserToken());

  const handleAccountLogin = async (): Promise<void> => {
    setLocalError(null);
    setIsOAuthStarting(true);
    try {
      const data = await authApi.startOAuthLogin();
      window.location.href = data.authorize_url;
    } catch {
      setLocalError('账号登录入口暂不可用，请稍后重试。');
      setIsOAuthStarting(false);
    }
  };

  const handlePurchase = (): void => {
    if (tokenInfo?.purchase_url) {
      window.location.href = tokenInfo.purchase_url;
      return;
    }
    if (hasOAuthSession) {
      window.location.href = '/payment/purchase';
      return;
    }
    void handleAccountLogin();
  };

  const handleContinuePurchase = (): void => {
    window.location.href = '/payment/purchase';
  };

  // -----------------------------------------------------------------------
  // Still verifying an existing stored token
  // -----------------------------------------------------------------------
  if (isVerifying) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          background: '#f0f2f5',
        }}
      >
        <Spin size="large" tip="正在验证登录状态..." />
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Login state is valid — render children
  // -----------------------------------------------------------------------
  if (serviceToken && isValid) {
    return <>{children}</>;
  }

  // -----------------------------------------------------------------------
  // Login state was invalid / expired — show error with retry
  // -----------------------------------------------------------------------
  if (serviceToken && !isValid && !isVerifying) {
    const isExpired = tokenInfo?.reason === 'token_expired';

    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          background: '#f0f2f5',
          padding: 24,
        }}
      >
        <Card style={{ maxWidth: 480, width: '100%', textAlign: 'center' }}>
          <Result
            status="warning"
            title={isExpired ? '服务已到期' : '登录状态已失效'}
            subTitle={
              isExpired
                ? '当前服务已过期，请购买或续费后继续使用。'
                : '您的登录状态可能已失效或被停用，请重新授权账号登录后继续使用。'
            }
            extra={
              <Space direction="vertical" style={{ width: '100%' }}>
                {isExpired && (
                  <Button
                    type="primary"
                    icon={<LoginOutlined />}
                    loading={isOAuthStarting}
                    onClick={handlePurchase}
                  >
                    购买或续费
                  </Button>
                )}
                <Button
                  type={isExpired ? 'default' : 'primary'}
                  icon={<LoginOutlined />}
                  loading={isOAuthStarting}
                  onClick={() => {
                    clearToken();
                    setLocalError(null);
                    void handleAccountLogin();
                  }}
                >
                  重新授权账号
                </Button>
              </Space>
            }
          />
        </Card>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // No token — full-page account authorization
  // -----------------------------------------------------------------------
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
        padding: 24,
      }}
    >
      <Card
        style={{
          maxWidth: 480,
          width: '100%',
          borderRadius: 12,
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.18)',
        }}
        styles={{ body: { padding: 40 } }}
      >
        <Space
          direction="vertical"
          size="large"
          style={{ width: '100%', textAlign: 'center' }}
        >
          <LoginOutlined
            style={{ fontSize: 48, color: '#1a1a2e', marginBottom: 16 }}
          />

          <Title level={3} style={{ margin: 0 }}>
            学术辅助平台
          </Title>

          <Text type="secondary">
            请使用账号授权登录后继续使用学术辅助功能。
          </Text>

          {localError && (
            <Text type="danger" style={{ display: 'block' }}>
              {localError}
            </Text>
          )}

          <Button
            type="primary"
            size="large"
            block
            icon={<LoginOutlined />}
            loading={isOAuthStarting}
            onClick={handleAccountLogin}
            style={{ height: 48 }}
          >
            授权账号登录
          </Button>

          {hasOAuthSession && (
            <Button
              type="primary"
              size="large"
              block
              loading={isOAuthStarting}
              onClick={handleContinuePurchase}
            >
              继续购买
            </Button>
          )}
        </Space>
      </Card>
    </div>
  );
}

export default ServiceTokenGuard;

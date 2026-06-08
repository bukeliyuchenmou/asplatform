import { useEffect, useState, type ReactNode } from 'react';
import { Button, Card, Result, Space, Spin, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../services/authApi';
import {
  createPayment,
  listPaymentProducts,
  type PaymentProduct,
} from '../services/paymentApi';
import {
  getOAuthOpenid,
  getOAuthUserToken,
  setOAuthOpenid,
  setPaymentWaitingOrderNo,
} from '../utils/oauthSession';

const { Text, Title } = Typography;

export default function PaymentPurchasePage() {
  const navigate = useNavigate();
  const [openid] = useState<string>(getOAuthOpenid());
  const [userToken] = useState<string>(getOAuthUserToken());
  const [products, setProducts] = useState<PaymentProduct[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [creatingProductId, setCreatingProductId] = useState<string>('');
  const [isOAuthStarting, setIsOAuthStarting] = useState<boolean>(false);

  useEffect(() => {
    if (!openid) {
      setIsLoading(false);
      return;
    }

    async function loadProducts() {
      setIsLoading(true);
      try {
        const data = await listPaymentProducts();
        setProducts(data);
      } catch {
        setError('load_products_failed');
      } finally {
        setIsLoading(false);
      }
    }

    void loadProducts();
  }, [openid]);

  const handleAccountLogin = async (): Promise<void> => {
    setError('');
    setIsOAuthStarting(true);
    try {
      const data = await authApi.startOAuthLogin();
      window.location.href = data.authorize_url;
    } catch {
      setError('oauth_start_failed');
      setIsOAuthStarting(false);
    }
  };

  const handleCreatePayment = async (product: PaymentProduct): Promise<void> => {
    if (!openid || !userToken) {
      setError('missing_openid');
      return;
    }

    setCreatingProductId(product.product_id);
    try {
      setOAuthOpenid(openid);
      const data = await createPayment({
        product_id: product.product_id,
        user_token: userToken,
        state: 'oauth_purchase',
      });
      setPaymentWaitingOrderNo(data.third_order_no);
      window.location.href = data.pay_url;
    } catch {
      setError('create_payment_failed');
    } finally {
      setCreatingProductId('');
    }
  };

  if (!openid || !userToken) {
    return (
      <PageFrame>
        <Result
          status="warning"
          title="账号登录状态已失效"
          subTitle={<Text type="secondary">请重新使用账号登录后继续购买。</Text>}
          extra={
            <Button
              type="primary"
              loading={isOAuthStarting}
              onClick={() => {
                void handleAccountLogin();
              }}
            >
              使用账号登录
            </Button>
          }
        />
      </PageFrame>
    );
  }

  if (error) {
    return (
      <PageFrame>
        <Result
          status="error"
          title="无法继续购买"
          subTitle={<Text type="secondary">错误信息：{error}</Text>}
          extra={
            <Button type="primary" onClick={() => navigate('/frontend/bio', { replace: true })}>
              返回分析工具
            </Button>
          }
        />
      </PageFrame>
    );
  }

  return (
    <PageFrame width={720}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Result
          status="info"
          title="继续购买"
          subTitle={<Text type="secondary">账号已登录，请选择产品并完成支付。</Text>}
        />

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="正在加载产品..." />
          </div>
        ) : products.length > 0 ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {products.map((product) => (
              <Card key={product.product_id} size="small">
                <Space
                  align="center"
                  style={{ width: '100%', justifyContent: 'space-between' }}
                >
                  <div>
                    <Title level={5} style={{ margin: 0 }}>
                      {product.name}
                    </Title>
                    {product.description && (
                      <Text type="secondary">{product.description}</Text>
                    )}
                    {product.price_label && (
                      <div>
                        <Text strong>{product.price_label}</Text>
                      </div>
                    )}
                  </div>
                  <Button
                    type="primary"
                    loading={creatingProductId === product.product_id}
                    onClick={() => {
                      void handleCreatePayment(product);
                    }}
                  >
                    购买
                  </Button>
                </Space>
              </Card>
            ))}
          </Space>
        ) : (
          <Result status="warning" title="暂无可购买产品" />
        )}
      </Space>
    </PageFrame>
  );
}

function PageFrame({
  children,
  width = 520,
}: {
  children: ReactNode;
  width?: number;
}) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
        padding: 24,
      }}
    >
      <Card style={{ width: '100%', maxWidth: width }}>{children}</Card>
    </div>
  );
}

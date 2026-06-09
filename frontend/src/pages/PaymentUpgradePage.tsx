import { useEffect, useState, type ReactNode } from 'react';
import { Button, Card, Result, Space, Spin, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  createPayment,
  getUpgradeContext,
  type PaymentProduct,
} from '../services/paymentApi';
import { useServiceToken } from '../hooks/useServiceToken';
import { setPaymentWaitingOrderNo } from '../utils/oauthSession';

const { Text, Title } = Typography;

export default function PaymentUpgradePage() {
  const navigate = useNavigate();
  const { serviceToken, isValid, isVerifying } = useServiceToken();
  const [products, setProducts] = useState<PaymentProduct[]>([]);
  const [currentSlug, setCurrentSlug] = useState<string>('experience');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [creatingProductId, setCreatingProductId] = useState<string>('');

  useEffect(() => {
    if (isVerifying) {
      return;
    }
    if (!serviceToken || !isValid) {
      setIsLoading(false);
      return;
    }
    const validServiceToken = serviceToken;

    async function loadProducts() {
      setIsLoading(true);
      try {
        const data = await getUpgradeContext(validServiceToken);
        setCurrentSlug(data.current_slug);
        setProducts(data.products);
      } catch {
        setError('load_products_failed');
      } finally {
        setIsLoading(false);
      }
    }

    void loadProducts();
  }, [isValid, isVerifying, serviceToken]);

  const handleCreatePayment = async (product: PaymentProduct): Promise<void> => {
    if (!serviceToken || !isValid) {
      setError('missing_service_token');
      return;
    }

    setCreatingProductId(product.product_id);
    try {
      const data = await createPayment({
        product_id: product.product_id,
        service_token: serviceToken,
        state: 'oauth_upgrade',
      });
      setPaymentWaitingOrderNo(data.third_order_no);
      window.location.href = data.pay_url;
    } catch {
      setError('create_payment_failed');
    } finally {
      setCreatingProductId('');
    }
  };

  if (isVerifying) {
    return (
      <PageFrame>
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin tip="正在验证服务状态..." />
        </div>
      </PageFrame>
    );
  }

  if (!serviceToken || !isValid) {
    return (
      <PageFrame>
        <Result
          status="warning"
          title="需要先登录"
          subTitle={<Text type="secondary">请先进入分析工具并完成服务令牌验证。</Text>}
          extra={
            <Space>
              <Button onClick={() => navigate(-1)}>关闭</Button>
              <Button type="primary" onClick={() => navigate('/frontend/bio', { replace: true })}>
                返回分析工具
              </Button>
            </Space>
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
          title="无法创建升级订单"
          subTitle={<Text type="secondary">错误信息：{error}</Text>}
          extra={
            <Space>
              <Button onClick={() => navigate(-1)}>关闭</Button>
              <Button type="primary" onClick={() => navigate('/frontend/bio', { replace: true })}>
                返回分析工具
              </Button>
            </Space>
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
          title="升级产品"
          subTitle={<Text type="secondary">当前套餐：{currentSlug}。可选择同级续费或更高等级升级。</Text>}
          extra={<Button onClick={() => navigate(-1)}>关闭</Button>}
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
                    {product.is_current && (
                      <div>
                        <Text type="secondary" style={{color: "#1777ff"}}>当前套餐</Text>
                      </div>
                    )}
                    {product.is_downgrade && (
                      <div>
                        <Text type="danger">当前服务有效期内不可降级购买</Text>
                      </div>
                    )}
                  </div>
                  <Button
                    type="primary"
                    disabled={product.is_downgrade}
                    loading={creatingProductId === product.product_id}
                    onClick={() => {
                      void handleCreatePayment(product);
                    }}
                  >
                    {product.is_current ? '续费/加购' : '升级'}
                  </Button>
                </Space>
              </Card>
            ))}
          </Space>
        ) : (
          <Result status="warning" title="暂无可升级产品" />
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

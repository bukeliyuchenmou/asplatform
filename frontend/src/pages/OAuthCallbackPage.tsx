import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Result, Space, Spin, Typography } from 'antd';
import { authApi } from '../services/authApi';
import { useServiceToken } from '../hooks/useServiceToken';
import {
  createPayment,
  listPaymentProducts,
  type PaymentProduct,
} from '../services/paymentApi';
import {
  getOAuthUserToken,
  setOAuthOpenid,
  setOAuthUserToken,
  setPaymentWaitingOrderNo,
} from '../utils/oauthSession';

const { Text, Title } = Typography;
const OAUTH_EXCHANGE_LOCK_PREFIX = 'oauth_exchange_code:';

export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const { verifyToken } = useServiceToken();
  const hasExchangedRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [purchaseRequired, setPurchaseRequired] = useState<boolean>(false);
  const [openid, setOpenid] = useState<string>('');
  const [products, setProducts] = useState<PaymentProduct[]>([]);
  const [isProductsLoading, setIsProductsLoading] = useState<boolean>(false);
  const [creatingProductId, setCreatingProductId] = useState<string>('');

  useEffect(() => {
    if (hasExchangedRef.current) {
      return;
    }
    hasExchangedRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get('error');
    const code = params.get('code');

    async function exchange() {
      if (oauthError) {
        setError(oauthError);
        return;
      }
      if (!code) {
        setError('missing_code');
        return;
      }

      const exchangeLockKey = `${OAUTH_EXCHANGE_LOCK_PREFIX}${code}`;
      try {
        if (sessionStorage.getItem(exchangeLockKey)) {
          return;
        }
        sessionStorage.setItem(exchangeLockKey, '1');
        const data = await authApi.exchangeOAuthCode(code);
        if (data.status === 'purchase_required' || !data.service_token) {
          setPurchaseRequired(true);
          setOpenid(data.openid);
          setOAuthOpenid(data.openid);
          if (data.user_token) {
            setOAuthUserToken(data.user_token);
          }
          window.history.replaceState(null, '', window.location.pathname);
          return;
        }
        const verified = await verifyToken(data.service_token);
        if (!verified) {
          setError('service_token_verify_failed');
          return;
        }
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/frontend/bio', { replace: true });
      } catch {
        sessionStorage.removeItem(exchangeLockKey);
        setError('exchange_failed');
      }
    }

    exchange();
  }, [navigate, verifyToken]);

  useEffect(() => {
    if (!purchaseRequired) {
      return;
    }

    async function loadProducts() {
      setIsProductsLoading(true);
      try {
        const data = await listPaymentProducts();
        setProducts(data);
      } catch {
        setError('load_products_failed');
      } finally {
        setIsProductsLoading(false);
      }
    }

    loadProducts();
  }, [purchaseRequired]);

  const handleCreatePayment = async (product: PaymentProduct): Promise<void> => {
    if (!openid) {
      setError('missing_openid');
      return;
    }

    setCreatingProductId(product.product_id);
    try {
      const data = await createPayment({
        product_id: product.product_id,
        user_token: getOAuthUserToken(),
        openid,
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

  if (error) {
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
        <Card style={{ width: '100%', maxWidth: 520 }}>
          <Result
            status="error"
            title="账号登录失败"
            subTitle={<Text type="secondary">错误信息：{error}</Text>}
            extra={
              <Button
                type="primary"
                onClick={() => navigate('/frontend/bio', { replace: true })}
              >
                重新授权账号
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  if (purchaseRequired) {
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
        <Card style={{ width: '100%', maxWidth: 720 }}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Result
              status="info"
              title="需要购买后继续使用"
              subTitle={
                <Text type="secondary">
                  账号已登录，请选择产品并完成支付。
                </Text>
              }
            />

            {isProductsLoading ? (
              <div style={{ textAlign: 'center', padding: 24 }}>
                <Spin tip="正在加载产品..." />
              </div>
            ) : products.length > 0 ? (
              <Space
                direction="vertical"
                size="middle"
                style={{ width: '100%' }}
              >
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
              <Result
                status="warning"
                title="暂无可购买产品"
                subTitle="请先在配置中添加产品信息。"
                extra={
                  <Button
                    type="primary"
                    onClick={() => navigate('/frontend/bio', { replace: true })}
                  >
                    重新授权账号
                  </Button>
                }
              />
            )}
          </Space>
        </Card>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Spin size="large" tip="正在完成账号登录..." />
    </div>
  );
}

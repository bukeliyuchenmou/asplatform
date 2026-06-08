import { useEffect, useState } from 'react';
import { Button, Card, Result, Spin, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getPaymentStatus } from '../services/paymentApi';
import { useServiceToken } from '../hooks/useServiceToken';
import {
  clearPaymentWaitingOrderNo,
  getOAuthOpenid,
  getOAuthUserToken,
  getPaymentWaitingOrderNo,
} from '../utils/oauthSession';

const { Text } = Typography;

export default function PaymentReturnPage() {
  const navigate = useNavigate();
  const { serviceToken: currentServiceToken, verifyToken } = useServiceToken();
  const [status, setStatus] = useState<string>('pending');
  const [error, setError] = useState<string>('');
  const hasOAuthSession = Boolean(getOAuthOpenid() && getOAuthUserToken());
  const userToken = getOAuthUserToken();
  const params = new URLSearchParams(window.location.search);
  const thirdOrderNo =
    params.get('third_order_no') ||
    params.get('thirdOrderNo') ||
    getPaymentWaitingOrderNo() ||
    '';

  useEffect(() => {
    if (!thirdOrderNo) {
      setError('missing_order_no');
      return;
    }

    let stopped = false;
    let attempts = 0;

    async function pollStatus() {
      try {
        const data = await getPaymentStatus(thirdOrderNo, {
          userToken,
          serviceToken: currentServiceToken || undefined,
        });
        if (stopped) {
          return;
        }
        setStatus(data.status);
        if (data.status === 'paid') {
          clearPaymentWaitingOrderNo();
          if (data.service_token) {
            const verified = await verifyToken(data.service_token);
            if (verified) {
              navigate('/frontend/bio', { replace: true });
              return;
            }
            setError('service_token_verify_failed');
          }
          return;
        }
      } catch {
        if (!stopped) {
          setError('query_payment_failed');
        }
        return;
      }

      attempts += 1;
      if (!stopped && attempts < 30) {
        window.setTimeout(() => {
          void pollStatus();
        }, 2000);
      } else if (!stopped) {
        setError('payment_sync_timeout');
      }
    }

    void pollStatus();

    return () => {
      stopped = true;
    };
  }, [currentServiceToken, navigate, thirdOrderNo, userToken, verifyToken]);

  const isPaid = status === 'paid';
  const canContinuePurchase = !isPaid && hasOAuthSession;
  const canContinueUpgrade = !isPaid && Boolean(currentServiceToken);

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
          status={isPaid ? 'success' : error ? 'warning' : 'info'}
          title={isPaid ? '支付已确认' : error ? '支付尚未完成' : '支付结果同步中'}
          subTitle={
            <Text type="secondary">
              {isPaid
                ? '支付通知已同步，正在进入分析工具。'
                : canContinuePurchase
                  ? '账号登录状态已保留，可以继续选择产品完成支付。'
                  : canContinueUpgrade
                    ? '服务登录状态已保留，可以继续选择产品完成升级。'
                    : '如果你已经完成支付，页面会自动等待支付通知同步。'}
            </Text>
          }
          extra={
            <>
              {!isPaid && !error && <Spin style={{ marginRight: 12 }} />}
              {canContinuePurchase && (
                <Button
                  type="primary"
                  onClick={() => navigate('/payment/purchase', { replace: true })}
                  style={{ marginRight: 12 }}
                >
                  继续购买
                </Button>
              )}
              {!canContinuePurchase && canContinueUpgrade && (
                <Button
                  type="primary"
                  onClick={() => navigate('/payment/upgrade', { replace: true })}
                  style={{ marginRight: 12 }}
                >
                  继续升级
                </Button>
              )}
              <Button
                type={canContinuePurchase || canContinueUpgrade ? 'default' : 'primary'}
                onClick={() => navigate('/frontend/bio', { replace: true })}
              >
                返回分析工具
              </Button>
            </>
          }
        />
      </Card>
    </div>
  );
}

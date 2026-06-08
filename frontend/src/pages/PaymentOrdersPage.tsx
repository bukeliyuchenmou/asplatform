import { useEffect, useState } from 'react';
import { Button, Empty, Result, Space, Spin, Table, Tag, Typography } from 'antd';
import { ShoppingCartOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  listPaymentOrders,
  type PaymentOrderRecord,
} from '../services/paymentApi';
import { useServiceToken } from '../hooks/useServiceToken';

const { Text, Title } = Typography;

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function formatNumber(value?: number | null): string {
  if (value === undefined || value === null) return '-';
  return Number(value).toLocaleString('zh-CN');
}

function statusTag(status: string) {
  const color = status === 'paid' ? 'green' : status === 'pending' ? 'gold' : 'default';
  const label = status === 'paid' ? '已支付' : status === 'pending' ? '待支付' : status;
  return <Tag color={color}>{label}</Tag>;
}

export default function PaymentOrdersPage() {
  const navigate = useNavigate();
  const { serviceToken, tokenInfo, isValid } = useServiceToken();
  const [orders, setOrders] = useState<PaymentOrderRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = serviceToken;
    if (!token || !isValid || tokenInfo?.source === 'manual') {
      setIsLoading(false);
      return;
    }

    async function loadOrders() {
      setIsLoading(true);
      setError('');
      try {
        setOrders(await listPaymentOrders(token));
      } catch {
        setError('订单记录加载失败');
      } finally {
        setIsLoading(false);
      }
    }

    void loadOrders();
  }, [isValid, serviceToken, tokenInfo?.source]);

  if (tokenInfo?.source === 'manual') {
    return (
      <Result
        status="info"
        title="手动服务令牌没有订单记录"
        subTitle={<Text type="secondary">订单记录只展示通过账号登录和支付创建的订单。</Text>}
      />
    );
  }

  if (error) {
    return (
      <Result
        status="error"
        title={error}
        extra={<Button onClick={() => window.location.reload()}>重新加载</Button>}
      />
    );
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>订单记录</Title>
          <Text type="secondary">查看当前账号的购买、续费和升级记录。</Text>
        </div>
        <Button
          type="primary"
          icon={<ShoppingCartOutlined />}
          onClick={() => navigate('/payment/upgrade')}
        >
          购买产品
        </Button>
      </Space>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin tip="正在加载订单记录..." />
        </div>
      ) : (
        <Table
          rowKey="third_order_no"
          dataSource={orders}
          locale={{ emptyText: <Empty description="暂无订单记录" /> }}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1180 }}
          columns={[
            {
              title: '订单号',
              dataIndex: 'third_order_no',
              width: 190,
              render: (value: string) => <Text copyable>{value}</Text>,
            },
            {
              title: '产品',
              dataIndex: 'product_name',
              render: (_: string, row: PaymentOrderRecord) => (
                <Space direction="vertical" size={0}>
                  <Text>{row.product_name || row.product_id}</Text>
                  {row.product_slug && <Tag>{row.product_slug}</Tag>}
                </Space>
              ),
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: statusTag,
            },
            {
              title: '金额',
              dataIndex: 'paid_amount',
              width: 100,
              render: formatNumber,
            },
            {
              title: '额度',
              dataIndex: 'issued_ai_quota',
              width: 120,
              render: formatNumber,
            },
            {
              title: '有效期',
              dataIndex: 'duration_days',
              width: 100,
              render: (value?: number | null) => (value ? `${value} 天` : '-'),
            },
            {
              title: 'Token 状态',
              dataIndex: 'issued_token_is_active',
              width: 110,
              render: (value?: boolean | null) => {
                if (value === undefined || value === null) return '-';
                return value ? <Tag color="green">有效</Tag> : <Tag>已停用</Tag>;
              },
            },
            {
              title: '到期时间',
              dataIndex: 'issued_token_expires_at',
              width: 170,
              render: formatDate,
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 170,
              render: formatDate,
            },
            {
              title: '支付时间',
              dataIndex: 'paid_at',
              width: 170,
              render: formatDate,
            },
          ]}
        />
      )}
    </Space>
  );
}

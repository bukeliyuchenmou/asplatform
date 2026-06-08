import api from './api';

export interface PaymentProduct {
  product_id: string;
  slug?: 'experience' | 'basic' | 'pro' | string;
  name: string;
  description?: string;
  price?: number | string;
  quota?: number | string;
  duration_days?: number | string;
  price_label?: string;
  is_current?: boolean;
  is_downgrade?: boolean;
  raw?: unknown;
}

export interface CreatePaymentResponse {
  third_order_no: string;
  request_id: string;
  pay_url: string;
  expires_in?: number;
  product?: PaymentProduct;
}

export interface PaymentStatus {
  third_order_no: string;
  request_id?: string;
  status: string;
  product_id: string;
  service_token?: string;
  issued_ai_quota?: number;
  created_at?: string;
  updated_at?: string;
}

export interface PaymentOrderRecord {
  third_order_no: string;
  request_id?: string;
  product_id: string;
  product_slug?: string | null;
  product_name?: string | null;
  product_price?: number | null;
  product_quota?: number | null;
  duration_days?: number | null;
  paid_amount?: number | null;
  paid_at?: string | null;
  issued_ai_quota?: number | null;
  issued_token_id?: number | null;
  issued_token_expires_at?: string | null;
  issued_token_is_active?: boolean | null;
  status: string;
  created_at?: string;
  updated_at?: string;
}

export async function listPaymentProducts(): Promise<PaymentProduct[]> {
  const response = await api.get<{ products: PaymentProduct[] }>('/api/payment/products');
  return response.data.products;
}

export async function getUpgradeContext(serviceToken: string): Promise<{
  current_slug: string;
  products: PaymentProduct[];
}> {
  const response = await api.get<{ current_slug: string; products: PaymentProduct[] }>(
    '/api/payment/upgrade-context',
    { params: { service_token: serviceToken } },
  );
  return response.data;
}

export async function createPayment(data: {
  product_id: string;
  openid?: string;
  user_token?: string;
  service_token?: string;
  state?: string;
}): Promise<CreatePaymentResponse> {
  const response = await api.post<CreatePaymentResponse>('/api/payment/create', data);
  return response.data;
}

export async function listPaymentOrders(serviceToken: string): Promise<PaymentOrderRecord[]> {
  const response = await api.get<{ orders: PaymentOrderRecord[] }>('/api/payment/orders', {
    params: { service_token: serviceToken },
  });
  return response.data.orders;
}

export async function getPaymentStatus(
  thirdOrderNo: string,
  options?: {
    userToken?: string;
    serviceToken?: string;
  },
): Promise<PaymentStatus> {
  const response = await api.get<PaymentStatus>(`/api/payment/status/${thirdOrderNo}`, {
    params: {
      ...(options?.userToken ? { user_token: options.userToken } : {}),
      ...(options?.serviceToken ? { service_token: options.serviceToken } : {}),
    },
  });
  return response.data;
}

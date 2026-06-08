export interface AdminUser {
  id: number;
  username: string;
  full_name?: string;
  email?: string;
  is_active: boolean;
  group_id?: number;
  group?: { id: number; name: string };
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface VerifyTokenResponse {
  valid: boolean;
  permissions?: string;
  ai_quota?: number;
  used_quota?: number;
  expires_at?: string;
  detail?: string;
  reason?: 'invalid_token' | 'token_expired' | 'token_inactive' | 'permission_denied';
  source?: 'manual' | 'oauth';
  entitlement_level?: 'experience' | 'basic' | 'pro' | string | null;
  purchase_url?: string;
}

export interface OAuthExchangeResponse {
  openid: string;
  user_token?: string;
  status?: 'ok' | 'purchase_required';
  service_token?: string;
  permissions?: string;
  ai_quota?: number;
  used_quota?: number;
  expires_at?: string;
  purchase_url?: string;
}

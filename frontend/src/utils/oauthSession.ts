const OAUTH_OPENID_KEY = 'oauth_openid';
const OAUTH_USER_TOKEN_KEY = 'oauth_user_token';
const PAYMENT_WAITING_ORDER_KEY = 'payment_waiting_order_no';

export function getOAuthOpenid(): string {
  return sessionStorage.getItem(OAUTH_OPENID_KEY) || '';
}

export function setOAuthOpenid(openid: string): void {
  sessionStorage.setItem(OAUTH_OPENID_KEY, openid);
}

export function clearOAuthOpenid(): void {
  sessionStorage.removeItem(OAUTH_OPENID_KEY);
}

export function getOAuthUserToken(): string {
  return sessionStorage.getItem(OAUTH_USER_TOKEN_KEY) || '';
}

export function setOAuthUserToken(userToken: string): void {
  sessionStorage.setItem(OAUTH_USER_TOKEN_KEY, userToken);
}

export function clearOAuthUserToken(): void {
  sessionStorage.removeItem(OAUTH_USER_TOKEN_KEY);
}

export function clearOAuthSession(): void {
  clearOAuthOpenid();
  clearOAuthUserToken();
}

export function getPaymentWaitingOrderNo(): string {
  return sessionStorage.getItem(PAYMENT_WAITING_ORDER_KEY) || '';
}

export function setPaymentWaitingOrderNo(thirdOrderNo: string): void {
  sessionStorage.setItem(PAYMENT_WAITING_ORDER_KEY, thirdOrderNo);
}

export function clearPaymentWaitingOrderNo(): void {
  sessionStorage.removeItem(PAYMENT_WAITING_ORDER_KEY);
}

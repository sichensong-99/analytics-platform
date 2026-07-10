import jwt from 'jsonwebtoken';

// JWT secret:签发"通行证"用的密钥。
// 生产环境必须是随机长字符串,放在环境变量里(经 Key Vault 注入)。
// 不设默认值:缺失就报错(fail-closed),绝不静默退回一个公开的默认密钥
// ——否则任何看过源码的人都能伪造登录 token。
function getJwtSecret(): string {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error(
      'JWT_SECRET is not set — refusing to sign/verify tokens. ' +
      'A hardcoded fallback signing key would let anyone forge auth tokens.',
    );
  }
  return secret;
}

export interface UserPayload {
  email: string;
  name: string;
  role: string;
}

// 签发一个"通行证"(token),7 天内有效
export function signToken(payload: UserPayload): string {
  return jwt.sign(payload, getJwtSecret(), { expiresIn: '7d' });
}

// 验证一个"通行证"是不是合法的
export function verifyToken(token: string): UserPayload | null {
  try {
    return jwt.verify(token, getJwtSecret()) as UserPayload;
  } catch {
    return null;
  }
}
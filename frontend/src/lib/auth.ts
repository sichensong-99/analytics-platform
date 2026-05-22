import jwt from 'jsonwebtoken';

// JWT secret:签发"通行证"用的密钥
// 生产环境必须是随机长字符串,放在环境变量里
const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-in-production';

export interface UserPayload {
  email: string;
  name: string;
  role: string;
}

// 签发一个"通行证"(token),7 天内有效
export function signToken(payload: UserPayload): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: '7d' });
}

// 验证一个"通行证"是不是合法的
export function verifyToken(token: string): UserPayload | null {
  try {
    return jwt.verify(token, JWT_SECRET) as UserPayload;
  } catch {
    return null;
  }
}
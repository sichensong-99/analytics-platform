import { NextRequest, NextResponse } from 'next/server';
import bcrypt from 'bcryptjs';
import { findUser } from '@/lib/users';
import { signToken } from '@/lib/auth';

export async function POST(req: NextRequest) {
  // 接收前端传来的邮箱和密码
  const { email, password } = await req.json();

  // 查找用户
  const user = findUser(email);
  if (!user) {
    return NextResponse.json(
      { error: 'Invalid email or password' },
      { status: 401 }
    );
  }

  // 验证密码
  const valid = bcrypt.compareSync(password, user.passwordHash);
  if (!valid) {
    return NextResponse.json(
      { error: 'Invalid email or password' },
      { status: 401 }
    );
  }

  // 签发 token
  const token = signToken({
    email: user.email,
    name: user.name,
    role: user.role,
  });

  // 把 token 放进 cookie 返回给浏览器
  const response = NextResponse.json({ success: true, name: user.name });
  response.cookies.set('auth-token', token, {
    httpOnly: true, // 防止 JavaScript 读取(更安全)
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * 7, // 7 天
    path: '/',
  });
  return response;
}
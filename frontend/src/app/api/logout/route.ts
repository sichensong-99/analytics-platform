import { NextResponse } from 'next/server';

export async function POST() {
  // 删除 token cookie,然后跳转到登录页
  const response = NextResponse.redirect(
    new URL('/', process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000')
  );
  response.cookies.delete('auth-token');
  return response;
}
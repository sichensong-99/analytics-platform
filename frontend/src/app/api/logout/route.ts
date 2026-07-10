import { NextResponse } from 'next/server';

export async function POST() {
  // 用相对 Location '/' 发重定向,不读 req.url。
  // 原因:Azure Container Apps 里 req.url 是容器内部地址(...:3000),
  // 用它拼绝对 URL 会把内部主机名+3000 端口暴露给浏览器 → 外网无法解析。
  // 相对路径 '/' 让浏览器按当前公网域名自己拼,本地/线上都对。
  const response = new NextResponse(null, {
    status: 307,
    headers: { Location: '/' },
  });
  // 清除 token cookie(同 set 一个立即过期的空值,确保 Path 一致被覆盖)
  response.cookies.set('auth-token', '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    expires: new Date(0),
    path: '/',
  });
  return response;
}
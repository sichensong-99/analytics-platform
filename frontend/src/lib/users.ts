// MVP 阶段:用户写死在代码里。
// 生产环境会改成数据库 + SSO,这是最简单的能跑版本。

import bcrypt from 'bcryptjs';

// 密码统一是 "password123",bcrypt 加密后存这里
// 实际部署时每个人改成自己的密码
export const users = [
  {
    email: 'leader@company.com',
    name: 'Team Leader',
    passwordHash: bcrypt.hashSync('password123', 10),
    role: 'admin',
  },
  {
    email: 'member1@company.com',
    name: 'Team Member 1',
    passwordHash: bcrypt.hashSync('password123', 10),
    role: 'viewer',
  },
  {
    email: 'member2@company.com',
    name: 'Team Member 2',
    passwordHash: bcrypt.hashSync('password123', 10),
    role: 'viewer',
  },
];

export function findUser(email: string) {
  return users.find((u) => u.email === email);
}
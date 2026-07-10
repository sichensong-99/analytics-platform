// One-off: create/update the first admin in Table Storage.
// Run from frontend/ so it uses frontend/node_modules.
import bcrypt from 'bcryptjs';
import { TableClient } from '@azure/data-tables';

const [, , email, password, name] = process.argv;
const conn = process.env.AZURE_TABLES_CONNECTION_STRING;

if (!conn) { console.error('Set AZURE_TABLES_CONNECTION_STRING first.'); process.exit(1); }
if (!email || !password) {
  console.error('Usage: node scripts/seed-admin.mjs "<email>" "<password>" "<name>"');
  process.exit(1);
}

const client = TableClient.fromConnectionString(conn, 'users');
try { await client.createTable(); } catch (e) { if (e?.statusCode !== 409) throw e; }

await client.upsertEntity({
  partitionKey: 'user',
  rowKey: email.trim().toLowerCase(),
  email: email.trim().toLowerCase(),
  name: name || 'Admin',
  role: 'admin',
  passwordHash: bcrypt.hashSync(password, 10),
  createdAt: new Date().toISOString(),
}, 'Replace');

console.log(`Seeded admin: ${email} (role=admin)`);
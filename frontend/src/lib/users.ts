// User store backed by Azure Table Storage.
// Admin-managed: created/updated via /admin (next slice). Server-side only —
// the connection string lives in route handlers, never reaches the browser.

import bcrypt from 'bcryptjs';
import { TableClient, odata } from '@azure/data-tables';

const CONN = process.env.AZURE_TABLES_CONNECTION_STRING || '';
const TABLE = 'users';
const PARTITION = 'user';

export interface AppUser {
  email: string;
  name: string;
  role: string;
  passwordHash: string;
  createdAt: string;
}

function client(): TableClient {
  if (!CONN) throw new Error('AZURE_TABLES_CONNECTION_STRING is not set');
  return TableClient.fromConnectionString(CONN, TABLE);
}

function rowKey(email: string): string {
  return email.trim().toLowerCase();
}

// Look up one user by email; null if not found.
export async function findUser(email: string): Promise<AppUser | null> {
  try {
    const e = await client().getEntity(PARTITION, rowKey(email));
    return {
      email: (e.email as string) ?? rowKey(email),
      name: (e.name as string) ?? '',
      role: (e.role as string) ?? 'viewer',
      passwordHash: (e.passwordHash as string) ?? '',
      createdAt: (e.createdAt as string) ?? '',
    };
  } catch {
    return null; // 404 from Table Storage -> not found
  }
}

// List all users (admin view) — no password hashes.
export async function listUsers(): Promise<Omit<AppUser, 'passwordHash'>[]> {
  const out: Omit<AppUser, 'passwordHash'>[] = [];
  const entities = client().listEntities({
    queryOptions: { filter: odata`PartitionKey eq ${PARTITION}` },
  });
  for await (const e of entities) {
    out.push({
      email: (e.email as string) ?? (e.rowKey as string),
      name: (e.name as string) ?? '',
      role: (e.role as string) ?? 'viewer',
      createdAt: (e.createdAt as string) ?? '',
    });
  }
  out.sort((a, b) => a.email.localeCompare(b.email));
  return out;
}

// Create a user; throws if the email already exists.
export async function createUser(input: {
  email: string;
  name: string;
  role: string;
  password: string;
}): Promise<void> {
  await client().createEntity({
    partitionKey: PARTITION,
    rowKey: rowKey(input.email),
    email: rowKey(input.email),
    name: input.name,
    role: input.role,
    passwordHash: bcrypt.hashSync(input.password, 10),
    createdAt: new Date().toISOString(),
  });
}

export async function setUserRole(email: string, role: string): Promise<void> {
  await client().updateEntity(
    { partitionKey: PARTITION, rowKey: rowKey(email), role },
    'Merge',
  );
}

export async function setUserPassword(email: string, password: string): Promise<void> {
  await client().updateEntity(
    { partitionKey: PARTITION, rowKey: rowKey(email), passwordHash: bcrypt.hashSync(password, 10) },
    'Merge',
  );
}
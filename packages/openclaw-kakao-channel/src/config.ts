import { lstatSync, readFileSync } from "node:fs";
import { isAbsolute } from "node:path";
import type { OpenClawConfig } from "openclaw/plugin-sdk/channel-core";

export type Account = { accountId: "default"; enabled: boolean; port: number; secretFile: string;
  stateDir: string; bridgeId: string };
export const schema = { type: "object", additionalProperties: false, properties: {
  enabled: { type: "boolean", default: false },
  port: { type: "integer", minimum: 1024, maximum: 65535, default: 29531 },
  secretFile: { type: "string" }, stateDir: { type: "string" }, bridgeId: { type: "string" },
} };
export function resolveAccount(cfg: OpenClawConfig, id?: string | null): Account {
  if (id && id !== "default") throw new Error("unsupported_account");
  const raw = cfg.channels?.["kakao-local"] as Partial<Account> | undefined;
  return { accountId: "default", enabled: raw?.enabled === true, port: raw?.port ?? 29531,
    secretFile: raw?.secretFile ?? "", stateDir: raw?.stateDir ?? "", bridgeId: raw?.bridgeId ?? "" };
}
export function loadToken(account: Account): string {
  if (!isAbsolute(account.secretFile) || !isAbsolute(account.stateDir) || !account.bridgeId) throw new Error("pairing_not_configured");
  const stat = lstatSync(account.secretFile);
  if (!stat.isFile() || stat.isSymbolicLink() || (process.platform !== "win32" && (stat.mode & 0o077))) throw new Error("insecure_secret_file");
  const token = readFileSync(account.secretFile, "utf8").trim();
  if (!/^[a-f0-9]{64}$/.test(token)) throw new Error("invalid_pairing_secret");
  return token;
}

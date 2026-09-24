// Test-only TLS termination for the real production build. Safari correctly
// upgrades resources under production CSP; serving that build over HTTP cannot
// test it faithfully. No production headers or application flags are relaxed.
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, unlinkSync, rmdirSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import os from "node:os";
import path from "node:path";

const frontendPort = 3106;
const tlsPort = 3105;
const upstream = new URL(process.env.CIVICSCOPE_TEST_API_URL ?? "http://127.0.0.1:8000");
if (!["127.0.0.1", "localhost"].includes(upstream.hostname) || upstream.protocol !== "http:") {
  throw new Error("Production browser tests require an HTTP loopback backend.");
}
const openssl = process.platform === "win32" && existsSync("C:/Program Files/Git/usr/bin/openssl.exe")
  ? "C:/Program Files/Git/usr/bin/openssl.exe" : "openssl";
const certificateDir = mkdtempSync(path.join(os.tmpdir(), "civicscope-test-tls-"));
const keyPath = path.join(certificateDir, "key.pem");
const certPath = path.join(certificateDir, "cert.pem");
let child;
let server;
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  server?.close();
  server?.closeAllConnections();
  child?.kill();
  for (const file of [keyPath, certPath]) if (existsSync(file)) unlinkSync(file);
  if (existsSync(certificateDir)) rmdirSync(certificateDir);
  process.exitCode = code;
}
process.once("SIGINT", () => stop());
process.once("SIGTERM", () => stop());
try {
  execFileSync(openssl, ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
    "-keyout", keyPath, "-out", certPath], { stdio: "ignore", windowsHide: true });
  const credentials = { key: readFileSync(keyPath), cert: readFileSync(certPath) };
  // Keep credentials in memory only. Windows test runners can terminate a
  // process tree without signals, so do not defer file cleanup until shutdown.
  unlinkSync(keyPath);
  unlinkSync(certPath);
  rmdirSync(certificateDir);
  child = spawn(process.execPath, [".next/standalone/server.js"], {
    env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: String(frontendPort) },
    stdio: "inherit", windowsHide: true,
  });
  child.once("exit", code => { if (!stopping) stop(code ?? 1); });
  child.once("error", () => stop(1));
  server = https.createServer(credentials, (request, response) => {
    const requestPath = request.url ?? "/";
    if (!requestPath.startsWith("/") || requestPath.startsWith("//")) {
      response.writeHead(400).end("Origin-form test requests only");
      return;
    }
    if (requestPath === "/__test/certificate.pem" && request.method === "GET") {
      // Public certificate only, for raw TLS test probes to trust this server.
      response.writeHead(200, { "Content-Type": "application/x-pem-file", "Cache-Control": "no-store" });
      response.end(credentials.cert);
      return;
    }
    // Client error reporting belongs to Next.js, all other API paths to FastAPI.
    const apiRequest = requestPath.startsWith("/api/") && !requestPath.startsWith("/api/client-errors");
    const targetOrigin = apiRequest ? upstream.origin : `http://127.0.0.1:${frontendPort}`;
    let target;
    try {
      target = new URL(requestPath, targetOrigin);
    } catch {
      response.writeHead(400).end("Invalid test request URL");
      return;
    }
    if (target.origin !== targetOrigin) {
      response.writeHead(400).end("Test proxy origin mismatch");
      return;
    }
    const headers = { ...request.headers, host: target.host };
    // Preserve same-origin semantics across local TLS termination. Never
    // rewrite a missing/foreign Origin, which the actual Next route must deny.
    if (!apiRequest && headers.origin === `https://127.0.0.1:${tlsPort}`) headers.origin = targetOrigin;
    // Constant destination hostname prevents a request target from becoming an
    // arbitrary outbound URL. Only the allowlisted loopback service port varies.
    const forwarded = http.request({
      hostname: "127.0.0.1", port: apiRequest ? Number(upstream.port || 80) : frontendPort,
      path: `${target.pathname}${target.search}`, method: request.method, headers,
    }, result => {
      response.writeHead(result.statusCode ?? 502, result.headers);
      result.pipe(response);
    });
    forwarded.on("error", () => { if (!response.headersSent) response.writeHead(502); response.end("Test upstream not ready"); });
    request.on("aborted", () => forwarded.destroy());
    request.pipe(forwarded);
  });
  server.once("error", () => stop(1));
  server.listen(tlsPort, "127.0.0.1");
} catch (error) {
  console.error("Production test server could not start:", error.message);
  stop(1);
}

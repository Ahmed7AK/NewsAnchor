#!/usr/bin/env node
// Serve public/ locally. With --refresh <minutes>, also fetch news on start and on that interval.
//   PORT  port to listen on (default 3000)
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { runFetch } from '../src/build.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(root, 'public');
const port = Number(process.env.PORT) || 3000;
const refreshArg = process.argv.indexOf('--refresh');
const refreshMinutes = refreshArg === -1 ? 0 : Number(process.argv[refreshArg + 1]) || 60;

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json',
};

const server = http.createServer(async (req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405).end();
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  } catch {
    res.writeHead(400).end();
    return;
  }
  let file = path.join(publicDir, path.normalize(pathname));
  if (file !== publicDir && !file.startsWith(publicDir + path.sep)) {
    res.writeHead(403).end();
    return;
  }
  try {
    let info = await stat(file);
    if (info.isDirectory()) {
      file = path.join(file, 'index.html');
      info = await stat(file);
    }
    res.writeHead(200, {
      'content-type': TYPES[path.extname(file)] || 'application/octet-stream',
      'content-length': info.size,
      'cache-control': file.endsWith('.json') ? 'no-cache' : 'max-age=60',
    });
    if (req.method === 'HEAD') res.end();
    else createReadStream(file).pipe(res);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain' }).end('Not found');
  }
});

let fetching = false;
async function refresh() {
  if (fetching) return;
  fetching = true;
  try {
    await runFetch({
      configPath: path.resolve(process.env.FEEDS_FILE || path.join(root, 'feeds.json')),
      outDir: path.join(publicDir, 'data'),
      timeZone: process.env.NEWS_TZ || Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
  } catch (err) {
    console.error(`News refresh failed: ${err.message}`);
  } finally {
    fetching = false;
  }
}

server.listen(port, () => {
  console.log(`Daily Digest running at http://localhost:${port}`);
  if (refreshMinutes > 0) {
    console.log(`Fetching news now and every ${refreshMinutes} minutes…\n`);
    refresh();
    setInterval(refresh, refreshMinutes * 60_000).unref();
  }
});

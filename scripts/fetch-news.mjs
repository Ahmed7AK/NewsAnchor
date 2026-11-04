#!/usr/bin/env node
// Fetch every feed in feeds.json and update public/data/.
//   NEWS_TZ      IANA time zone that decides what "today" is (default: this machine's)
//   ARCHIVE_URL  published site to restore earlier days from (used by CI)
//   FEEDS_FILE   alternative feed list (default: feeds.json)
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { runFetch } from '../src/build.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

try {
  await runFetch({
    configPath: path.resolve(process.env.FEEDS_FILE || path.join(root, 'feeds.json')),
    outDir: path.join(root, 'public', 'data'),
    timeZone: process.env.NEWS_TZ || Intl.DateTimeFormat().resolvedOptions().timeZone,
    archiveUrl: process.env.ARCHIVE_URL || '',
  });
} catch (err) {
  console.error(`\n${err.message}`);
  process.exitCode = 1;
}

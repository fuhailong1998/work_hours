import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../', import.meta.url));
const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
await build({
  absWorkingDir: root,
  entryPoints: ['web/src/app.js'],
  outfile: 'web/static/app.js',
  bundle: true,
  minify: true,
  format: 'esm',
  define: { __APP_VERSION__: JSON.stringify(version) },
  logLevel: 'info',
});

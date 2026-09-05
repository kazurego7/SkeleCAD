// Source-only tests. The full viewer integration test requires local build assets.
const {readdirSync} = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const directory = path.join(root, 'skelecad/viewer/tests');
const files = readdirSync(directory).filter(name => name.endsWith('.test.cjs') && name !== 'simple_viewer.test.cjs').sort();
if (!files.length) throw new Error('No source tests found');
console.log('Source checks exclude simple_viewer.test.cjs, which requires generated models and private input images.');
const result = spawnSync(process.execPath, ['--test', ...files.map(name => path.join(directory, name))], {cwd: root, stdio: 'inherit'});
if (result.error) throw result.error;
process.exitCode = result.status === null ? 1 : result.status;

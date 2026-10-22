#!/usr/bin/env node
// Render a motion-graphics template (or any composition of your own Remotion
// project) to a file Resolve can import. Prints one JSON line on stdout.
//
//   node render.mjs --list                                   # templates + metadata
//   node render.mjs --template LowerThird --props '{"name":"Ada"}' --out lt.mov
//   node render.mjs --template Text3D --still 60 --out frame.png
//   node render.mjs --project ~/my-remotion --entry src/index.ts --list
//
// Options: --props-file f.json  --codec h264|h265|prores|vp9  --alpha
//          --progress-file f  --browser /path/to/chrome  --gl angle|swangle|egl|vulkan
//          --concurrency N  --scale 0.5
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {getCompositions, renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CATALOG = JSON.parse(fs.readFileSync(path.join(HERE, 'templates.json'), 'utf8'));

const parseArgs = (argv) => {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) out[key] = true;
    else out[key] = argv[++i];
  }
  return out;
};

const args = parseArgs(process.argv.slice(2));
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const fail = (message) => {
  emit({success: false, error: message});
  process.exit(1);
};

const projectDir = path.resolve(args.project || HERE);
const isOwnProject = projectDir === HERE;
const findEntry = () => {
  if (args.entry) return path.resolve(projectDir, args.entry);
  for (const c of ['src/index.jsx', 'src/index.tsx', 'src/index.ts', 'src/index.js', 'remotion/index.ts', 'remotion/index.tsx']) {
    if (fs.existsSync(path.join(projectDir, c))) return path.join(projectDir, c);
  }
  return fail(`No Remotion entry found in ${projectDir}; pass --entry (the file that calls registerRoot).`);
};
const entry = findEntry();

// Bundling (webpack) is the slow part, so cache the bundle by a hash of the
// project's source files and reuse it until something changes.
const sourceHash = () => {
  const h = createHash('sha1');
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir).sort()) {
      if (['node_modules', 'out', '.cache', '.git', 'build', 'dist'].includes(name)) continue;
      const p = path.join(dir, name);
      const st = fs.statSync(p);
      if (st.isDirectory()) walk(p);
      else h.update(`${p}:${st.size}:${st.mtimeMs}`);
    }
  };
  walk(projectDir);
  h.update(entry);
  return h.digest('hex').slice(0, 16);
};

const getBundle = async () => {
  const cacheRoot = path.join(HERE, '.cache');
  const dir = path.join(cacheRoot, `bundle-${sourceHash()}`);
  if (fs.existsSync(path.join(dir, 'index.html'))) return dir;
  fs.mkdirSync(cacheRoot, {recursive: true});
  for (const old of fs.readdirSync(cacheRoot)) {
    if (old.startsWith('bundle-')) fs.rmSync(path.join(cacheRoot, old), {recursive: true, force: true});
  }
  return bundle({entryPoint: entry, outDir: dir, enableCaching: true});
};

const browserExecutable = args.browser || process.env.DAVINCI_RESOLVE_MCP_MOTION_BROWSER || process.env.REMOTION_BROWSER_EXECUTABLE || null;
const gl = args.gl || process.env.DAVINCI_RESOLVE_MCP_MOTION_GL || (process.platform === 'linux' ? 'swangle' : 'angle');
const chromiumOptions = {gl};

const progressFile = args['progress-file'];
const writeProgress = (obj) => {
  if (!progressFile) return;
  try {
    fs.writeFileSync(progressFile, JSON.stringify({...obj, at: Date.now()}));
  } catch {
    // progress is best-effort
  }
};

const readProps = () => {
  if (args['props-file']) return JSON.parse(fs.readFileSync(args['props-file'], 'utf8'));
  if (args.props) return JSON.parse(args.props);
  return {};
};

const main = async () => {
  writeProgress({stage: 'bundling', progress: 0});
  const serveUrl = await getBundle();

  if (args.list) {
    const comps = await getCompositions(serveUrl, {browserExecutable, chromiumOptions});
    const meta = Object.fromEntries(CATALOG.map((t) => [t.id, t]));
    emit({
      success: true,
      project: projectDir,
      templates: comps.map((c) => ({
        id: c.id,
        description: isOwnProject ? meta[c.id]?.description : undefined,
        category: isOwnProject ? meta[c.id]?.category : undefined,
        transparent: isOwnProject ? Boolean(meta[c.id]?.transparent) : undefined,
        width: c.width,
        height: c.height,
        fps: c.fps,
        durationSeconds: +(c.durationInFrames / c.fps).toFixed(3),
        defaultProps: c.defaultProps,
      })),
    });
    return;
  }

  const id = args.template || fail('--template is required');
  const props = readProps();
  const composition = await selectComposition({serveUrl, id, inputProps: props, browserExecutable, chromiumOptions});
  const meta = isOwnProject ? CATALOG.find((t) => t.id === id) : null;
  const alpha = Boolean(args.alpha) || Boolean(meta?.transparent) || props.transparentBackground === true;

  const outDir = path.join(HERE, 'out');
  if (args.still !== undefined) {
    const frame = args.still === true ? Math.floor(composition.durationInFrames / 2) : Number(args.still);
    const out = path.resolve(args.out || path.join(outDir, `${id}-${Date.now()}.png`));
    fs.mkdirSync(path.dirname(out), {recursive: true});
    await renderStill({serveUrl, composition, inputProps: props, output: out, frame, imageFormat: 'png', browserExecutable, chromiumOptions, scale: Number(args.scale) || 1});
    emit({success: true, out, still: true, frame, width: composition.width, height: composition.height, alpha});
    return;
  }

  const codec = args.codec || (alpha ? 'prores' : 'h264');
  const ext = {h264: 'mp4', h265: 'mp4', prores: 'mov', vp9: 'webm', vp8: 'webm'}[codec] || 'mp4';
  const out = path.resolve(args.out || path.join(outDir, `${id}-${Date.now()}.${ext}`));
  fs.mkdirSync(path.dirname(out), {recursive: true});
  const alphaOptions = alpha
    ? codec === 'prores'
      ? {proResProfile: '4444', imageFormat: 'png', pixelFormat: 'yuva444p10le'}
      : codec.startsWith('vp')
        ? {imageFormat: 'png', pixelFormat: 'yuva420p'}
        : {}
    : {};
  if (alpha && !['prores', 'vp8', 'vp9'].includes(codec)) {
    process.stderr.write(`note: ${codec} has no alpha channel; use prores or vp9 for transparency\n`);
  }
  const started = Date.now();
  await renderMedia({
    serveUrl,
    composition,
    inputProps: props,
    codec,
    outputLocation: out,
    browserExecutable,
    chromiumOptions,
    concurrency: args.concurrency ? Number(args.concurrency) : Math.max(1, Math.floor(os.cpus().length / 2)),
    scale: Number(args.scale) || 1,
    ...alphaOptions,
    onProgress: ({progress, renderedFrames, encodedFrames}) => writeProgress({stage: 'rendering', progress, renderedFrames, encodedFrames}),
  });
  writeProgress({stage: 'done', progress: 1});
  emit({
    success: true,
    out,
    codec,
    alpha: Boolean(alphaOptions.pixelFormat),
    width: composition.width,
    height: composition.height,
    fps: composition.fps,
    durationInFrames: composition.durationInFrames,
    durationSeconds: +(composition.durationInFrames / composition.fps).toFixed(3),
    renderSeconds: +((Date.now() - started) / 1000).toFixed(1),
  });
};

main().catch((err) => {
  writeProgress({stage: 'error', error: String(err?.message || err)});
  fail(String(err?.stack || err?.message || err));
});

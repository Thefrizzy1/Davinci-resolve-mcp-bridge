import * as THREE from 'three';

/** Deterministic PRNG so every render of the same props is frame-identical. */
export const seeded = (seed = 1) => {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/** Soft round sprite for points. */
export const dotTexture = () => {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.4, 'rgba(255,255,255,0.6)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
};

/** White text on transparent canvas → texture + aspect ratio. */
export const textTexture = (text, {fontFamily, fontWeight = 900, px = 220} = {}) => {
  const c = document.createElement('canvas');
  const g = c.getContext('2d');
  const font = `${fontWeight} ${px}px ${fontFamily}`;
  g.font = font;
  const w = Math.ceil(g.measureText(text).width + px * 0.4);
  const h = Math.ceil(px * 1.35);
  c.width = Math.max(4, w);
  c.height = h;
  g.font = font;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = '#ffffff';
  g.fillText(text, c.width / 2, h / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return {texture: tex, aspect: c.width / c.height};
};

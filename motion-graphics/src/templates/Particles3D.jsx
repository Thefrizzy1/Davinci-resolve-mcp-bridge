import React, {useMemo} from 'react';
import * as THREE from 'three';
import {useThree} from '@react-three/fiber';
import {ThreeCanvas} from '@remotion/three';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {dotTexture, seeded} from './three-helpers.js';
import {Overlay} from './Overlay.jsx';
import {outro} from '../anim.js';

const Field = ({count, color, color2, size, speed, spread}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const {camera} = useThree();
  const t = (frame / fps) * speed;

  const {geometry, texture} = useMemo(() => {
    const rand = seeded(7);
    const n = Math.max(10, Math.min(Number(count) || 4000, 60000));
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    const a = new THREE.Color(color);
    const b = new THREE.Color(color2);
    for (let i = 0; i < n; i++) {
      const r = spread * Math.cbrt(rand());
      const th = rand() * Math.PI * 2;
      const ph = Math.acos(2 * rand() - 1);
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th) * 0.6;
      pos[i * 3 + 2] = r * Math.cos(ph);
      const c = a.clone().lerp(b, rand());
      col.set([c.r, c.g, c.b], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    return {geometry: g, texture: dotTexture()};
  }, [count, color, color2, spread]);

  camera.position.set(Math.sin(t * 0.15) * 1.5, Math.cos(t * 0.11) * 0.8, 7 - t * 0.3);
  camera.lookAt(0, 0, 0);
  const fade = Math.min(1, frame / 15) * outro(frame, durationInFrames, 15);

  return (
    <points geometry={geometry} rotation={[t * 0.03, t * 0.06, 0]}>
      <pointsMaterial size={size} map={texture} vertexColors transparent opacity={fade} depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation />
    </points>
  );
};

export const Particles3D = (props) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: props.transparentBackground ? 'transparent' : props.background}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 60, position: [0, 0, 9]}} gl={{alpha: true, antialias: true, preserveDrawingBuffer: true}}>
        <Field {...props} />
      </ThreeCanvas>
      <Overlay title={props.title} color={props.titleColor} fontFamily={props.fontFamily} />
    </AbsoluteFill>
  );
};

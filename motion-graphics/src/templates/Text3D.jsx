import React, {useMemo} from 'react';
import * as THREE from 'three';
import {ThreeCanvas} from '@remotion/three';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {textTexture} from './three-helpers.js';
import {Overlay} from './Overlay.jsx';
import {outro} from '../anim.js';

// Extrusion by stacking alpha-tested slices of the same text texture: works
// with any installed font and any script, with no font files to ship.
const Title = ({text, color, sideColor, accent, depth, fontFamily, fontWeight}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const {texture, aspect} = useMemo(() => textTexture(String(text), {fontFamily, fontWeight}), [text, fontFamily, fontWeight]);
  const viewW = 2 * Math.tan((50 / 2) * (Math.PI / 180)) * 10 * (width / height);
  const planeW = Math.min(viewW * 0.78, aspect * 2.6);
  const planeH = planeW / aspect;
  const slices = Math.max(2, Math.min(Number(depth) || 24, 60));
  const thickness = planeH * 0.22;

  const enter = spring({frame, fps, config: {damping: 16, stiffness: 90, mass: 0.9}});
  const t = frame / fps;
  const rotY = interpolate(enter, [0, 1], [-1.1, 0]) + Math.sin(t * 0.9) * 0.18;
  const rotX = interpolate(enter, [0, 1], [0.5, 0]) + Math.sin(t * 0.6) * 0.05;
  const out = outro(frame, durationInFrames, 14);
  const side = new THREE.Color(sideColor);
  const lightX = interpolate(frame, [0, durationInFrames], [-9, 9]);

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[lightX, 2, 5]} intensity={60} color={accent} distance={30} />
      <directionalLight position={[0, 3, 8]} intensity={1.6} />
      <group rotation={[rotX, rotY, 0]} scale={0.6 + 0.4 * enter}>
        {Array.from({length: slices}, (_, i) => {
          const k = i / (slices - 1);
          return (
            <mesh key={i} position={[0, 0, -k * thickness]}>
              <planeGeometry args={[planeW, planeH]} />
              <meshBasicMaterial map={texture} transparent alphaTest={0.45} opacity={out} color={side.clone().multiplyScalar(1 - 0.55 * k)} side={THREE.DoubleSide} />
            </mesh>
          );
        })}
        <mesh position={[0, 0, 0.002]}>
          <planeGeometry args={[planeW, planeH]} />
          <meshStandardMaterial map={texture} transparent alphaTest={0.45} opacity={out} color={color} emissive={color} emissiveMap={texture} emissiveIntensity={0.55} metalness={0.3} roughness={0.35} />
        </mesh>
      </group>
    </>
  );
};

export const Text3D = (props) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: props.transparentBackground ? 'transparent' : props.background}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 50, position: [0, 0, 10]}} gl={{alpha: true, antialias: true, preserveDrawingBuffer: true}}>
        <Title {...props} />
      </ThreeCanvas>
      <Overlay subtitle={props.subtitle} color={props.color} fontFamily={props.fontFamily} delay={24} />
    </AbsoluteFill>
  );
};

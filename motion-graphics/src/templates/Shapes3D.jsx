import React from 'react';
import {useThree} from '@react-three/fiber';
import {ThreeCanvas} from '@remotion/three';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Overlay} from './Overlay.jsx';
import {outro} from '../anim.js';

const GEOMETRY = {
  torusKnot: <torusKnotGeometry args={[1.6, 0.5, 256, 48]} />,
  torus: <torusGeometry args={[1.8, 0.6, 64, 128]} />,
  icosahedron: <icosahedronGeometry args={[2.2, 1]} />,
  box: <boxGeometry args={[2.6, 2.6, 2.6]} />,
  sphere: <sphereGeometry args={[2.2, 64, 64]} />,
};

const Scene = ({shape, color, color2, wireframe, metalness, roughness}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const {camera} = useThree();
  const t = frame / fps;
  const enter = spring({frame, fps, config: {damping: 13, stiffness: 80}});
  const out = outro(frame, durationInFrames, 15);
  camera.position.set(Math.sin(t * 0.3) * 9, 1.5 + Math.sin(t * 0.2), Math.cos(t * 0.3) * 9);
  camera.lookAt(0, 0, 0);

  return (
    <>
      <ambientLight intensity={0.6} />
      <pointLight position={[Math.sin(t) * 6, 4, Math.cos(t) * 6]} intensity={120} color={color2} distance={40} />
      <pointLight position={[-Math.sin(t * 0.7) * 6, -3, -Math.cos(t * 0.7) * 6]} intensity={80} color={color} distance={40} />
      <directionalLight position={[3, 6, 4]} intensity={2.2} />
      <hemisphereLight args={['#ffffff', '#222233', 0.6]} />
      <mesh rotation={[t * 0.4, t * 0.6, 0]} scale={enter * out}>
        {GEOMETRY[shape] || GEOMETRY.torusKnot}
        <meshStandardMaterial color={color} metalness={metalness} roughness={roughness} wireframe={wireframe} />
      </mesh>
    </>
  );
};

export const Shapes3D = (props) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: props.transparentBackground ? 'transparent' : props.background}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 45, position: [0, 0, 9]}} gl={{alpha: true, antialias: true, preserveDrawingBuffer: true}}>
        <Scene {...props} />
      </ThreeCanvas>
      <Overlay title={props.title} color={props.titleColor} fontFamily={props.fontFamily} />
    </AbsoluteFill>
  );
};

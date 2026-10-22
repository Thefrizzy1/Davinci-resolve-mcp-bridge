import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease} from '../anim.js';

/** Optional HTML title layered over a 3D scene. */
export const Overlay = ({title, subtitle, color = '#fff', fontFamily, delay = 18}) => {
  const frame = useCurrentFrame();
  const {height} = useVideoConfig();
  const unit = height / 1080;
  if (!title && !subtitle) return null;
  const a = ease(frame, delay, 18);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', fontFamily, pointerEvents: 'none'}}>
      {title ? <div style={{color, fontSize: 120 * unit, fontWeight: 900, opacity: a, transform: `translateY(${(1 - a) * 30 * unit}px)`, textShadow: `0 ${8 * unit}px ${40 * unit}px rgba(0,0,0,0.6)`}}>{title}</div> : null}
      {subtitle ? <div style={{position: 'absolute', bottom: height * 0.2, color, opacity: 0.85 * a, fontSize: 44 * unit, fontWeight: 600, letterSpacing: 8 * unit, textTransform: 'uppercase'}}>{subtitle}</div> : null}
    </AbsoluteFill>
  );
};

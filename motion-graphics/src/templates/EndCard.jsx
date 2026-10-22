import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease, outro, pop} from '../anim.js';

export const EndCard = ({headline, handle, cta, background, accent, textColor, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const unit = height / 1080;
  const out = outro(frame, durationInFrames, 20);
  const head = pop(frame, fps, 4);
  const handleIn = ease(frame, 16, 16);
  const ctaIn = pop(frame, fps, 26);
  const pulse = 1 + 0.03 * Math.sin((frame / fps) * Math.PI * 2);

  const rings = [0, 1, 2].map((i) => {
    const r = interpolate((frame + i * 25) % 75, [0, 75], [0.2, 1.4]);
    const o = interpolate((frame + i * 25) % 75, [0, 75], [0.35, 0]);
    return (
      <div key={i} style={{position: 'absolute', left: width * 0.5, top: height * 0.5, width: 900 * unit * r, height: 900 * unit * r, marginLeft: -450 * unit * r, marginTop: -450 * unit * r, borderRadius: '50%', border: `${3 * unit}px solid ${accent}`, opacity: o}} />
    );
  });

  return (
    <AbsoluteFill style={{background, fontFamily, justifyContent: 'center', alignItems: 'center', opacity: out}}>
      {rings}
      <div style={{textAlign: 'center', zIndex: 1}}>
        <div style={{color: textColor, fontSize: 110 * unit, fontWeight: 900, opacity: head, transform: `scale(${0.85 + 0.15 * head})`}}>{headline}</div>
        <div style={{color: accent, fontSize: 52 * unit, fontWeight: 700, marginTop: 18 * unit, opacity: handleIn, transform: `translateY(${(1 - handleIn) * 20 * unit}px)`}}>{handle}</div>
        {cta ? (
          <div style={{display: 'inline-block', marginTop: 48 * unit, padding: `${20 * unit}px ${54 * unit}px`, borderRadius: 999, background: accent, color: '#fff', fontSize: 40 * unit, fontWeight: 800, transform: `scale(${ctaIn * pulse})`}}>
            {cta}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

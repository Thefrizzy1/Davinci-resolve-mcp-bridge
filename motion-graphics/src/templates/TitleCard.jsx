import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease, outro, pop} from '../anim.js';

export const TitleCard = ({title, subtitle, background, background2, accent, textColor, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, height, durationInFrames} = useVideoConfig();
  const unit = height / 1080;
  const out = outro(frame, durationInFrames, 18);
  const angle = interpolate(frame, [0, durationInFrames], [120, 160]);
  const rule = ease(frame, 10, 20);
  const sub = ease(frame, 18, 18);
  const letters = [...String(title)];

  return (
    <AbsoluteFill style={{background: `linear-gradient(${angle}deg, ${background}, ${background2})`, justifyContent: 'center', alignItems: 'center', fontFamily}}>
      <div style={{opacity: out, textAlign: 'center', transform: `scale(${1 + (1 - out) * 0.04})`}}>
        <div style={{color: textColor, fontSize: 150 * unit, fontWeight: 900, letterSpacing: -2 * unit, lineHeight: 1}}>
          {letters.map((ch, i) => {
            const p = pop(frame, fps, i * 1.6);
            return (
              <span key={i} style={{display: 'inline-block', whiteSpace: 'pre', opacity: p, transform: `translateY(${(1 - p) * 60 * unit}px)`}}>
                {ch}
              </span>
            );
          })}
        </div>
        <div style={{height: 8 * unit, width: 260 * unit, margin: `${34 * unit}px auto`, background: accent, transform: `scaleX(${rule})`, borderRadius: 4 * unit}} />
        {subtitle ? (
          <div style={{color: textColor, opacity: 0.85 * sub, fontSize: 46 * unit, fontWeight: 500, letterSpacing: 6 * unit, textTransform: 'uppercase', transform: `translateY(${(1 - sub) * 20 * unit}px)`}}>
            {subtitle}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

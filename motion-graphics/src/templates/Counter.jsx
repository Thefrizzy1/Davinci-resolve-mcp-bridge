import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease, outro} from '../anim.js';

export const Counter = ({from, to, decimals, prefix, suffix, label, color, accent, fontSize, fontFamily}) => {
  const frame = useCurrentFrame();
  const {height, durationInFrames} = useVideoConfig();
  const unit = height / 1080;
  const countEnd = Math.max(2, Math.round(durationInFrames * 0.65));
  const value = interpolate(frame, [0, countEnd], [Number(from), Number(to)], {extrapolateRight: 'clamp', easing: Easing.out(Easing.exp)});
  const formatted = value.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
  const inT = ease(frame, 0, 10);
  const labelIn = ease(frame, 8, 14);
  const done = frame >= countEnd ? ease(frame, countEnd, 10) : 0;
  const out = outro(frame, durationInFrames, 10);

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', fontFamily, opacity: Math.min(inT, out)}}>
      <div style={{color, fontSize: fontSize * unit, fontWeight: 900, fontVariantNumeric: 'tabular-nums', letterSpacing: -3 * unit, transform: `scale(${1 + done * 0.05 - done * done * 0.05})`, textShadow: `0 ${8 * unit}px ${30 * unit}px rgba(0,0,0,0.5)`}}>
        <span style={{color: accent}}>{prefix}</span>
        {formatted}
        <span style={{color: accent}}>{suffix}</span>
      </div>
      {label ? (
        <div style={{color, opacity: 0.85 * labelIn, fontSize: 44 * unit, fontWeight: 700, letterSpacing: 8 * unit, textTransform: 'uppercase', transform: `translateY(${(1 - labelIn) * 16 * unit}px)`}}>
          {label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

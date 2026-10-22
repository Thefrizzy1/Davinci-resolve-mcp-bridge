import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {outro, pop} from '../anim.js';

export const KineticText = ({text, color, highlight, wordsPerSecond, fontSize, shadow, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, height, durationInFrames} = useVideoConfig();
  const unit = height / 1080;
  const out = outro(frame, durationInFrames, 12);
  const step = fps / Math.max(0.5, Number(wordsPerSecond) || 3);
  const words = String(text).split(/\s+/).filter(Boolean);

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: '0 8%', fontFamily}}>
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `${0.12 * fontSize * unit}px ${0.28 * fontSize * unit}px`, opacity: out}}>
        {words.map((raw, i) => {
          const hot = /^\*.*\*$/.test(raw);
          const word = hot ? raw.slice(1, -1) : raw;
          const p = pop(frame, fps, i * step, {damping: 11, stiffness: 180, mass: 0.5});
          return (
            <span
              key={i}
              style={{
                color: hot ? highlight : color,
                fontSize: fontSize * unit,
                fontWeight: 900,
                lineHeight: 1.05,
                display: 'inline-block',
                opacity: Math.min(1, p * 1.5),
                transform: `translateY(${(1 - p) * 0.5 * fontSize * unit}px) scale(${0.6 + 0.4 * p})`,
                textShadow: shadow ? `0 ${6 * unit}px ${24 * unit}px rgba(0,0,0,0.55)` : 'none',
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

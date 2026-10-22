import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease, outro, pop} from '../anim.js';

export const LowerThird = ({name, title, accent, textColor, panelColor, position, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const unit = height / 1080;
  const right = position === 'right';
  const inT = pop(frame, fps, 0);
  const out = outro(frame, durationInFrames, 14);
  const bar = ease(frame, 2, 14);
  const nameIn = ease(frame, 6, 16);
  const titleIn = ease(frame, 12, 16);
  const slide = (1 - inT) * 60 * unit * (right ? 1 : -1) + (1 - out) * 80 * unit * (right ? 1 : -1);

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          bottom: height * 0.12,
          [right ? 'right' : 'left']: width * 0.06,
          transform: `translateX(${slide}px)`,
          opacity: Math.min(inT, out),
          display: 'flex',
          flexDirection: right ? 'row-reverse' : 'row',
          alignItems: 'stretch',
          fontFamily,
        }}
      >
        <div style={{width: 10 * unit, background: accent, transform: `scaleY(${bar})`, transformOrigin: 'bottom'}} />
        <div
          style={{
            background: panelColor,
            padding: `${22 * unit}px ${36 * unit}px`,
            clipPath: `inset(0 ${right ? 0 : (1 - bar) * 100}% 0 ${right ? (1 - bar) * 100 : 0}%)`,
            textAlign: right ? 'right' : 'left',
          }}
        >
          <div style={{color: textColor, fontSize: 58 * unit, fontWeight: 800, letterSpacing: -0.5, opacity: nameIn, transform: `translateY(${(1 - nameIn) * 20 * unit}px)`}}>
            {name}
          </div>
          {title ? (
            <div style={{color: accent, fontSize: 32 * unit, fontWeight: 600, marginTop: 6 * unit, textTransform: 'uppercase', letterSpacing: 3 * unit, opacity: titleIn, transform: `translateY(${(1 - titleIn) * 14 * unit}px)`}}>
              {title}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

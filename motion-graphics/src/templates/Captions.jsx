import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ease} from '../anim.js';

// Word timings: use the transcript's own words when present, else spread the
// words of the segment evenly (weighted by length) across its duration.
const wordsOf = (seg) => {
  if (Array.isArray(seg.words) && seg.words.length) {
    return seg.words.map((w) => ({text: String(w.word ?? w.text ?? '').trim(), start: Number(w.start), end: Number(w.end)}));
  }
  const parts = String(seg.text || '').split(/\s+/).filter(Boolean);
  const total = parts.reduce((n, p) => n + p.length + 1, 0) || 1;
  const span = Number(seg.end) - Number(seg.start);
  let t = Number(seg.start);
  return parts.map((p) => {
    const d = (span * (p.length + 1)) / total;
    const w = {text: p, start: t, end: t + d};
    t += d;
    return w;
  });
};

export const Captions = ({segments, fontSize, color, highlight, box, boxColor, position, wordByWord, uppercase, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const unit = height / 1080;
  const t = frame / fps;
  const seg = (segments || []).find((s) => t >= Number(s.start) && t < Number(s.end));
  if (!seg) return <AbsoluteFill />;
  const appear = ease(frame, Math.round(Number(seg.start) * fps), 5);
  const words = wordsOf(seg);
  const placement = position === 'top' ? {top: height * 0.08} : position === 'center' ? {top: '45%'} : {bottom: height * 0.09};

  return (
    <AbsoluteFill style={{alignItems: 'center', fontFamily}}>
      <div
        style={{
          position: 'absolute',
          ...placement,
          maxWidth: '84%',
          textAlign: 'center',
          padding: box ? `${12 * unit}px ${26 * unit}px` : 0,
          background: box ? boxColor : 'transparent',
          borderRadius: 14 * unit,
          opacity: appear,
          transform: `translateY(${(1 - appear) * 12 * unit}px)`,
          fontSize: fontSize * unit,
          fontWeight: 800,
          lineHeight: 1.2,
          textTransform: uppercase ? 'uppercase' : 'none',
          textShadow: box ? 'none' : `0 ${3 * unit}px ${12 * unit}px rgba(0,0,0,0.8)`,
        }}
      >
        {words.map((w, i) => {
          const active = wordByWord && t >= w.start && t < w.end;
          return (
            <span key={i} style={{color: active ? highlight : color, display: 'inline-block', transform: `scale(${active ? 1.06 : 1})`, marginRight: '0.28em'}}>
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

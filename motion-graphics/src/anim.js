import {interpolate, spring, Easing} from 'remotion';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};

/** 0 → 1 over `length` frames starting at `start`, eased. */
export const ease = (frame, start, length, easing = Easing.out(Easing.cubic)) =>
  interpolate(frame, [start, start + length], [0, 1], {...clamp, easing});

/** Spring 0 → 1 that starts at `delay`. */
export const pop = (frame, fps, delay = 0, config = {damping: 14, stiffness: 140, mass: 0.6}) =>
  spring({frame: frame - delay, fps, config});

/** 1 while on screen, fading/sliding out over the last `outFrames`. */
export const outro = (frame, durationInFrames, outFrames = 15) =>
  interpolate(frame, [durationInFrames - outFrames, durationInFrames], [1, 0], {...clamp, easing: Easing.in(Easing.cubic)});

export const lerp = (a, b, t) => a + (b - a) * t;

import React from 'react';
import {Composition} from 'remotion';
import catalog from '../templates.json';
import {LowerThird} from './templates/LowerThird.jsx';
import {TitleCard} from './templates/TitleCard.jsx';
import {KineticText} from './templates/KineticText.jsx';
import {Captions} from './templates/Captions.jsx';
import {Counter} from './templates/Counter.jsx';
import {EndCard} from './templates/EndCard.jsx';
import {Particles3D} from './templates/Particles3D.jsx';
import {Text3D} from './templates/Text3D.jsx';
import {Shapes3D} from './templates/Shapes3D.jsx';

const COMPONENTS = {LowerThird, TitleCard, KineticText, Captions, Counter, EndCard, Particles3D, Text3D, Shapes3D};

// Size, fps and length come from templates.json but every render can override
// them through props: durationSeconds, fps, width, height. Captions also
// stretches to the end of its last segment.
const calculateMetadata = (template) => ({props}) => {
  const fps = Number(props.fps) || template.fps;
  let seconds = Number(props.durationSeconds) || template.durationSeconds;
  if (template.id === 'Captions' && !props.durationSeconds && Array.isArray(props.segments) && props.segments.length) {
    seconds = Math.max(...props.segments.map((s) => Number(s.end) || 0)) + 0.5;
  }
  return {
    fps,
    durationInFrames: Math.max(1, Math.round(seconds * fps)),
    width: Number(props.width) || template.width,
    height: Number(props.height) || template.height,
  };
};

export const RemotionRoot = () => (
  <>
    {catalog.map((template) => (
      <Composition
        key={template.id}
        id={template.id}
        component={COMPONENTS[template.id]}
        durationInFrames={Math.round(template.durationSeconds * template.fps)}
        fps={template.fps}
        width={template.width}
        height={template.height}
        defaultProps={template.defaultProps}
        calculateMetadata={calculateMetadata(template)}
      />
    ))}
  </>
);

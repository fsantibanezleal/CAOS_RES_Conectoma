import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Playback for a clip, in local state and driven by the frame clock.
 *
 * The first version of this advanced the frame by writing it into the URL: one router navigation and one
 * history entry per frame, five to ten times a second. That is why the App felt like a slide show. Here
 * the frame lives in component state while it plays, the URL is written only when the reader pauses (so a
 * shared link still opens on an exact frame), and the step is driven by `requestAnimationFrame` against
 * the real clock, so a dropped frame shortens the next step instead of stretching the clip.
 *
 * Paused by default. Stops when the tab is hidden, per the standing rule that nothing in this product
 * autoplays or keeps computing out of sight.
 */
export function usePlayback(frames: number, secondsPerFrame: number, options: {
  initial?: number;
  speed?: number;
  loop?: boolean;
  onPause?: (frame: number) => void;
} = {}) {
  const { initial = 0, speed = 1, loop = true, onPause } = options;
  const [frame, setFrame] = useState(initial);
  const [playing, setPlaying] = useState(false);
  const clock = useRef<{ raf: number; last: number; carry: number } | null>(null);
  const pauseHandler = useRef(onPause);
  pauseHandler.current = onPause;

  // a reader who moves the slider, or a case that changed under us, wins over whatever was playing
  useEffect(() => {
    setFrame((current) => (current < frames ? current : 0));
  }, [frames]);

  const stop = useCallback(() => {
    setPlaying(false);
    setFrame((current) => {
      pauseHandler.current?.(current);
      return current;
    });
  }, []);

  useEffect(() => {
    if (!playing || frames <= 1) return undefined;
    const step = Math.max(secondsPerFrame, 0.02) * 1000 / Math.max(speed, 0.05);
    const tick = (now: number) => {
      const state = clock.current;
      if (!state) return;
      const elapsed = now - state.last + state.carry;
      const advance = Math.floor(elapsed / step);
      if (advance > 0) {
        state.last = now;
        state.carry = elapsed - advance * step;
        setFrame((current) => {
          const next = current + advance;
          if (next < frames) return next;
          if (loop) return next % frames;
          setPlaying(false);
          return frames - 1;
        });
      }
      state.raf = window.requestAnimationFrame(tick);
    };
    clock.current = { raf: window.requestAnimationFrame(tick), last: performance.now(), carry: 0 };
    return () => {
      if (clock.current) window.cancelAnimationFrame(clock.current.raf);
      clock.current = null;
    };
  }, [playing, frames, secondsPerFrame, speed, loop]);

  useEffect(() => {
    const hide = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);

  return {
    frame,
    playing,
    setFrame: (value: number) => {
      setPlaying(false);
      setFrame(Math.min(Math.max(value, 0), Math.max(frames - 1, 0)));
    },
    play: () => setPlaying(true),
    pause: stop,
    toggle: () => (playing ? stop() : setPlaying(true)),
  };
}

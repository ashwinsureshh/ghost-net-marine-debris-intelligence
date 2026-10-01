import * as React from "react";

/**
 * Trajectory playback state, outside React.
 *
 * Playback advances every animation frame. Holding it in App state would
 * re-render the whole console sixty times a second; instead the player and the
 * map subscribe to this small store, so only the readout re-renders and the
 * map moves one marker imperatively.
 */
export interface PlaybackState {
  detectionId: string | null;
  direction: "forward" | "backward";
  /** 0 = detection, 1 = end of the exported horizon. */
  fraction: number;
  playing: boolean;
  speed: 1 | 2 | 4;
}

type Listener = (state: PlaybackState) => void;

const initial: PlaybackState = { detectionId: null, direction: "forward", fraction: 0, playing: false, speed: 1 };

function createStore() {
  let state = initial;
  const listeners = new Set<Listener>();
  return {
    get: () => state,
    set(patch: Partial<PlaybackState>) {
      state = { ...state, ...patch };
      listeners.forEach(l => l(state));
    },
    reset() { this.set({ ...initial }); },
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}

export const playback = createStore();

export function usePlayback(): PlaybackState {
  return React.useSyncExternalStore(playback.subscribe, playback.get, playback.get);
}

/** Seconds a full track takes at 1×. Slow enough to read the numbers. */
export const PLAYBACK_SECONDS = 8;

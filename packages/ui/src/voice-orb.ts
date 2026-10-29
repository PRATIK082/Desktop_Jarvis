// Voice orb component placeholder (accessible, reduced-motion aware).
export interface VoiceOrbProps {
  amplitude: number;
  state: "idle" | "listening" | "thinking" | "speaking" | "error";
  reducedMotion?: boolean;
}

export const VoiceOrb = (_props: VoiceOrbProps): JSX.Element => {
  throw new Error("VoiceOrb not yet implemented");
};

export function mapAnimationDuration(
  animated: boolean,
  prefersReducedMotion: boolean,
  durationMs: number
): number {
  return animated && !prefersReducedMotion ? durationMs : 0;
}

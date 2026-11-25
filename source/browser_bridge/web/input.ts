// Coordinates are normalized to the actual canvas rectangle, not its surrounding letterbox.
export function mapPoint(rect: { left: number; top: number; width: number; height: number }, x: number, y: number) {
  return { x: Math.max(0, Math.min(1, (x - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (y - rect.top) / rect.height)) };
}

// SITE_UPGRADE.md UX rule: if WebGL is unavailable, sections must fall back
// to a static equivalent with the same information.
export function hasWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

// SITE_UPGRADE.md 3D rule: OrbitControls off for touch pointers.
export function isCoarsePointer(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: coarse)").matches;
}

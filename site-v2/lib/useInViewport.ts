import { useEffect, useState, type RefObject } from "react";

// True while `ref` is on (or near) screen. Used to mount a WebGL Canvas only
// when visible and unmount it otherwise, so at most one GL context is live —
// browsers (and Opera GX's limiter) cap concurrent contexts, and HMR leaks them.
export function useInViewport(
  ref: RefObject<Element | null>,
  rootMargin = "200px"
) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), {
      rootMargin,
    });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, rootMargin]);
  return inView;
}

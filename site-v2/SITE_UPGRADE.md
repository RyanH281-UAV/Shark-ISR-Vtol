PROJECT CONTEXT
===============
Read AGENTS.md and PRODUCT.md before writing any code.

This prompt upgrades site-v2 with 3D visualisations and DOM-layer motion polish.
The site is a personal engineering portfolio for Ryan Hughes — autonomous VTOL
drone, ROS 2 guidance state machine, SEARCH→TRACK autonomy with no operator
in the loop. Audience: aerospace/GNC/autonomy hiring managers at Boeing,
Lockheed, Anduril, Shield AI, Joby, L3Harris, defence-tech startups, and
university research roles.

SKILLS ACTIVE IN THIS SESSION
==============================
- Impeccable design skill is installed. Apply it when generating any UI
  component. No generic SaaS patterns, no Inter or DM Sans, no gradient
  cards, no eyebrow-on-every-section scaffolding, no feature-tour bullet
  lists. Every visual decision must be earned by the engineering content.
- motion-dev-animations-skill is installed. Use it for all Framer Motion
  and GSAP animation code. Apply spring physics where appropriate.
  Respect the prefers-reduced-motion media query — globals.css already
  stubs this, maintain it throughout.

DESIGN TOKENS (match exactly, do not invent new values)
========================================================
  #0A0F14  background      #101820  panel
  #1C2933  lines            #E9F0F4  bright
  #C6D3DC  text             #7B8C99  muted
  #45B8AC  teal    — SEARCH state / primary accent
  #E8A33D  amber   — TRACK state / detection events
  #C2604F  red     — RTL state / failsafe
  #5A7A94  slate   — TRANSIT state

  Display:  Saira Condensed
  Body:     IBM Plex Sans
  Mono:     IBM Plex Mono  (all labels, data readouts, badges)
  Accent:   Fraunces Serif (warmth/accent moments only — never for UI chrome)
  NEVER use: Inter, DM Sans, or any system-ui fallback as a deliberate choice

HARDWARE NODES
==============
  A: Camera Module 3   — Sony IMX708 · CSI-2
  B: Hailo-8L AI HAT+  — 13 TOPS · PCIe Gen 3
  C: Raspberry Pi 5    — companion · uXRCE-DDS
  D: Pixhawk 6C Mini   — autopilot · PWM
  Signal flow: A → B → C → D

STATES
======
  TRANSIT #5A7A94 · SEARCH #45B8AC · TRACK #E8A33D · RTL #C2604F

NEXT.JS RULES (mandatory — do not skip any of these)
=====================================================
  - Every file using Canvas, useFrame, useThree, or any R3F hook:
    MUST have 'use client' as the very first line
  - Canvas must NEVER be rendered on the server. Pattern:

      import dynamic from 'next/dynamic'
      const StackCanvas = dynamic(() => import('./StackCanvas'), { ssr: false })

    Create a separate *Canvas.tsx for raw R3F content, wrap with
    dynamic import in the parent component file.
  - All Framer Motion components in App Router: 'use client' required
  - No useEffect, useState, or browser APIs in Server Components

UX RULES
========
  - WebGL fallback: if Canvas fails or WebGL unavailable, show a static
    diagram with identical information — plain divs, no Canvas dependency
  - All 3D interactive nodes: tabIndex={0}, onKeyDown Enter/Space fires
    the same handler as onClick
  - Loading state: Suspense fallback is a pulsing skeleton in #101820
  - Reduced motion: all animations must check
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
    and skip or snap to final state if true

3D RULES
========
  - Canvas background: transparent (alpha:true on the renderer)
  - Bloom only on emissive meshes — never on card surfaces
  - useFrame: check document.hidden and skip updates when tab is not visible
  - OrbitControls: disabled on mobile (pointer type touch)

FILE PATHS
==========
  New components: components/
  3D components:  components/3d/
  UI primitives:  components/ui/
  Do NOT create anything in app/ except updating the page that
  mounts these components. Do not move or rename existing files.
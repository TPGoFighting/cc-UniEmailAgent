# OpenAI / ChatGPT Design System

## AI Native Interface Specification (2026 Edition)

------

# 0. Vision

This design system is not intended to imitate a traditional SaaS dashboard.

The goal is to create:

> A calm, intelligent, AI-native operating environment.

The interface should feel:

- invisible
- ambient
- intelligent
- emotionally minimal
- context-driven
- cognitively lightweight

Users should feel like they are:

- thinking
- exploring
- conversing
- creating

—not “using software.”

------

# 1. Core Design Philosophy

## 1.1 Invisible UI

The interface must never dominate attention.

UI exists to support cognition.

The system should reduce:

- visual noise
- excessive navigation
- unnecessary decisions
- dashboard complexity
- button dependency

### Principle

```txt
Less interface.
More intelligence.
```

------

## 1.2 Context First

Traditional software:

```txt
Navigation → Function → Result
```

AI-native software:

```txt
Intent → Context → Intelligence → Result
```

The interface should prioritize:

- conversation
- intent capture
- memory
- continuity
- adaptive context

------

## 1.3 Emotional Tone

The interface should feel:

- calm
- premium
- thoughtful
- restrained
- cinematic
- trustworthy

Avoid:

- aggressive marketing aesthetics
- startup-style visuals
- gamification
- loud gradients
- excessive animations

------

# 2. Visual Language

## Keywords

```txt
minimalism
ambient computing
AI-native
post-SaaS
cognitive interface
soft futurism
calm intelligence
cinematic whitespace
```

------

# 3. Color System

## 3.1 Philosophy

Use:

- 95% neutral tones
- 5% accent color

Accent colors should indicate:

- intelligence
- active interaction
- focus state
- generation state

—not branding dominance.

------

## 3.2 Core Palette

| Token            | Value                  |
| ---------------- | ---------------------- |
| canvas           | #FFFFFF                |
| canvas-secondary | #F7F7F8                |
| surface          | #FAFAFA                |
| surface-elevated | #FFFFFF                |
| border-subtle    | #ECECEC                |
| border-soft      | rgba(0,0,0,0.06)       |
| text-primary     | #212121                |
| text-secondary   | #6E6E80                |
| text-muted       | #9A9AA5                |
| accent           | #10A37F                |
| accent-hover     | #0E9270                |
| dark-bg          | #202123                |
| dark-surface     | #2A2B32                |
| dark-border      | rgba(255,255,255,0.08) |
| dark-text        | #ECECF1                |

------

## 3.3 Color Usage Rules

### DO

- use large neutral spaces
- use subtle contrast
- use accent sparingly
- prioritize readability
- preserve calmness

### DO NOT

- use neon gradients excessively
- use pure black (#000000)
- use bright CTA colors everywhere
- create high visual aggression

------

# 4. Typography System

## 4.1 Typography Philosophy

Typography is the primary interface.

Text should feel:

- elegant
- breathable
- highly readable
- emotionally neutral
- premium

------

## 4.2 Font Stack

### Recommended

```css
font-family:
Inter,
SF Pro Display,
Söhne,
Geist,
system-ui,
sans-serif;
```

------

## 4.3 Type Scale

### Hero Heading

```css
font-size: 64px;
line-height: 1.05;
font-weight: 700;
letter-spacing: -0.04em;
```

### H1

```css
font-size: 48px;
line-height: 1.1;
font-weight: 650;
```

### H2

```css
font-size: 32px;
line-height: 1.2;
font-weight: 600;
```

### Body Large

```css
font-size: 18px;
line-height: 1.7;
font-weight: 400;
```

### Body

```css
font-size: 16px;
line-height: 1.65;
font-weight: 400;
```

### Caption

```css
font-size: 13px;
line-height: 1.5;
color: #9A9AA5;
```

------

# 5. Spacing System

## 5.1 Whitespace Philosophy

Whitespace is architecture.

Large breathing spaces create:

- calmness
- focus
- intelligence perception
- emotional premium feeling

------

## 5.2 Spacing Scale

```txt
4
8
12
16
24
32
48
64
96
128
160
```

------

## 5.3 Layout Rules

### Hero Sections

Minimum vertical breathing:

```css
padding-top: 140px;
padding-bottom: 140px;
```

### Content Width

```css
max-width: 1200px;
```

### Reading Width

```css
max-width: 720px;
```

------

# 6. Grid System

## Desktop

```txt
12-column grid
```

## Tablet

```txt
8-column grid
```

## Mobile

```txt
4-column grid
```

------

# 7. Component System

## 7.1 Input Composer

The input composer is the emotional center of the interface.

### Characteristics

- floating
- soft
- centered
- low visual noise
- large radius
- ambient shadow

------

### CSS Reference

```css
.ai-composer {
  border-radius: 28px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(255,255,255,0.8);
  backdrop-filter: blur(20px);
  box-shadow:
    0 2px 8px rgba(0,0,0,0.04),
    0 8px 32px rgba(0,0,0,0.03);
}
```

------

## 7.2 Sidebar

Sidebar should feel secondary.

### Rules

- low contrast
- compact width
- hover-based emphasis
- reduced visual weight
- content-first hierarchy

### Recommended Width

```css
width: 260px;
```

------

## 7.3 Cards

Cards should feel light and floating.

### Rules

- subtle borders
- minimal shadows
- large radius
- low elevation
- soft transitions

### CSS Reference

```css
.ai-card {
  border-radius: 24px;
  border: 1px solid rgba(0,0,0,0.06);
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(20px);
}
```

------

## 7.4 Buttons

Buttons should never dominate.

### Rules

- medium contrast
- soft hover
- no excessive glow
- restrained motion

### Primary Button

```css
background: #10A37F;
color: white;
border-radius: 999px;
```

### Hover

```css
transform: translateY(-1px);
opacity: 0.96;
```

------

# 8. Motion System

## 8.1 Motion Philosophy

Motion should feel:

- atmospheric
- fluid
- invisible
- intelligent
- cinematic

Animation should never feel playful.

------

## 8.2 Timing

### Standard

```css
transition-duration: 250ms;
```

### Ambient

```css
transition-duration: 400ms;
```

------

## 8.3 Easing

```css
cubic-bezier(0.22, 1, 0.36, 1)
```

------

## 8.4 Hover Behavior

### Recommended

```css
transform: translateY(-1px);
opacity: 0.98;
```

### Avoid

- bounce animations
- excessive scaling
- strong glow effects
- high-energy motion

------

# 9. AI Native UX Principles

## 9.1 Input Is The Homepage

The primary interaction surface should be:

- intent-driven
- conversational
- adaptive

The input field is more important than navigation.

------

## 9.2 Progressive Intelligence

Do not expose all functionality immediately.

Reveal capability contextually.

Users should discover intelligence naturally.

------

## 9.3 Reduce UI Dependency

The AI should:

- infer intent
- remember history
- reduce clicks
- reduce setup friction
- minimize configuration

------

## 9.4 Ambient Computing

The interface should increasingly disappear.

Long-term direction:

```txt
Software → Workspace → Environment
```

------

# 10. Accessibility

## Requirements

- WCAG AA minimum
- keyboard navigable
- high readability
- strong focus states
- reduced motion support

------

## Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
```

------

# 11. Tailwind Design Tokens

## Example

```js
module.exports = {
  theme: {
    extend: {
      colors: {
        canvas: '#FFFFFF',
        surface: '#F7F7F8',
        accent: '#10A37F',
        text: '#212121',
        muted: '#6E6E80'
      },
      borderRadius: {
        xl2: '24px',
        xl3: '32px'
      },
      boxShadow: {
        ambient:
          '0 2px 8px rgba(0,0,0,0.04), 0 8px 32px rgba(0,0,0,0.03)'
      }
    }
  }
}
```

------

# 12. Prompt Engineering For AI UI Generation

## AI UI Prompt

```txt
Design an AI-native interface inspired by OpenAI ChatGPT.

Style:
minimalist,
ambient,
calm intelligence,
post-SaaS,
cinematic whitespace,
soft monochrome palette,
subtle glassmorphism,
Apple-level typography,
large breathing spaces,
context-first interaction.

Avoid:
heavy dashboards,
startup aesthetics,
marketing sections,
visual clutter,
overly colorful components.

Mood:
future operating system,
creative cognition,
premium restraint,
ambient intelligence.
```

------

# 13. Future Interface Direction

## Phase 1

```txt
Chat UI
```

## Phase 2

```txt
Agent Workspace
```

## Phase 3

```txt
AI Operating System
```

## Phase 4

```txt
Ambient Intelligence
```

------

# 14. Final Principle

The future of interface design is not:

```txt
More UI.
```

It is:

```txt
More understanding.
```

The best AI interfaces eventually feel less like software,
and more like thought itself.
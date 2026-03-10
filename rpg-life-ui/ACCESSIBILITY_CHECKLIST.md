# Accessibility Checklist (WCAG 2.1 AA)

## Perceivable
- [ ] All images have alt text
- [ ] Color is not the only means of conveying information
- [ ] Text contrast ratio ≥ 4.5:1
- [ ] Text resizes up to 200% without loss of functionality

## Operable
- [ ] All functionality available via keyboard
- [ ] Keyboard focus is visible (`*:focus-visible` ring in index.css)
- [ ] No keyboard traps (useFocusTrap used in modals only)
- [ ] Skip to main content link present (SkipLink in MainLayout)
- [ ] Page titles are descriptive
- [ ] Keyboard shortcuts: `j` Journal, `s` Skills, `q` Quests, `p` Profile (Dashboard)

## Understandable
- [ ] Language is specified (`lang="en"` on `<html>`)
- [ ] Navigation is consistent
- [ ] Error messages are clear
- [ ] Labels on all form inputs

## Robust
- [ ] Valid HTML
- [ ] ARIA used correctly (`aria-current`, `aria-label`, `aria-hidden`, `role="progressbar"`)
- [ ] Works with screen readers (LiveRegion announces loading/loaded states)
- [ ] Works in different browsers

## Implementation Status
- [x] `src/hooks/useKeyboardNav.ts` — keyboard shortcut hook (skips inputs/textareas)
- [x] `src/hooks/useFocusTrap.ts` — focus trap hook for modals/dialogs
- [x] `src/components/accessibility/SkipLink.tsx` — skip to main content
- [x] `src/components/accessibility/LiveRegion.tsx` — screen reader announcements
- [x] `src/components/layout/MainLayout.tsx` — SkipLink added, `id="main-content"` on `<main>`
- [x] `src/components/layout/Sidebar.tsx` — `aria-current="page"`, `aria-hidden` on icons, focus-visible ring
- [x] `src/pages/Dashboard.tsx` — keyboard shortcuts, LiveRegion, progressbar ARIA
- [x] `src/index.css` — focus-visible ring, high contrast media query, prefers-reduced-motion

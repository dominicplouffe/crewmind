# Logo and wordmark

**The mark: a squad around one mind.** Three members joined to a centre, inside a rounded tile. It reads as a small org chart and as a constellation; it holds at 16 px and works in one colour.

- **Construction:** a 32-unit square with an 8-unit corner radius in `--color-accent`. A centre node (radius 3.6) and three member nodes (radius 2.4) at 10, 2 and 6 o'clock, joined by 2-unit strokes at 55% opacity, all in `--color-accent-text`.
- **Wordmark:** "nightsquad" in lower case, Inter Bold, tracking −0.03 em, set beside the mark at a gap of 0.55 × the mark's height. The product name stays lower case everywhere, as in the code and the CLI.
- **Clear space:** half the mark's width on every side.
- **Sizes:** 16 (favicon), 24–26 (navigation), 40 (sign-in), 56+ (onboarding).
- **Colour:** iris on any neutral; white tile with iris nodes on an iris background; single-colour black or white for print.
- **Don't:** recolour the nodes individually, add gradients or shadows to the mark, or animate it except for a fade.

Source: `web/src/ui/Logo.tsx` (`LogoMark`, `Logo`) and `web/public/icon.svg`.

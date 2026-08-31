# QuantOS workspace visual system

## Product read

QuantOS is a research instrument for a single quantitative researcher or a
small research team. It is not a marketing landing page and it is not a
trading terminal. The interface should make evidence easy to scan, parameters
safe to edit, and immutable Run identity easy to verify.

## Design direction

The workspace uses a bright research-console language with low motion and high
information density:

- design variance: 4/10;
- motion intensity: 2/10;
- visual density: 7/10;
- one light theme with cool neutral surfaces;
- one green product accent, with red and amber reserved for semantic market,
  risk, and health states;
- Manrope for interface copy and IBM Plex Mono for numbers, times, versions,
  parameters, and immutable identities.

## Layout invariants

- Keep the four product views and their hash routes stable.
- Keep the application navigation on one line at desktop widths.
- Display Run outcomes before strategy configuration and detailed charts.
- Use the strategy library as a compact left index, not as a card gallery.
- Use bordered surfaces only when they identify a distinct interactive or
  evidence boundary. Prefer whitespace and one divider between related rows.
- Use one 8px surface radius and one 6px control radius. Status chips may use a
  4px radius but must not become decorative pills.
- Numbers that affect a decision must be at least 18px. Body copy must be at
  least 13px. Operational metadata must be at least 10px.
- At widths below 820px, all asymmetric product layouts collapse to one column.

## Interaction and accessibility

- Motion is limited to hover, focus, active, and state transitions.
- Every control has a visible keyboard focus state.
- Green and red always accompany a number, label, or status word.
- Disabled controls remain legible and explain why they are unavailable.
- Loading, empty, offline, and failed states preserve the final component's
  footprint and use plain language.
- The page does not use color glows, decorative gradients, or animation loops.

## Redesign audit

Preserved:

- QuantOS wordmark and green accent;
- Overview, Strategies, Runs, and Data boundaries;
- result-first strategy summary;
- folder-style strategy selection;
- bilingual copy and hash navigation;
- read-only and live-trading-disabled safety messaging.

Retired:

- type smaller than 10px;
- nested cards with independent shadows;
- decorative pill labels and excessive rounding;
- oversized page titles and loose vertical gaps;
- gradient page backgrounds and gradient selected states;
- inconsistent 7px, 9px, 10px, 12px, 14px, 16px, and 18px surface radii.

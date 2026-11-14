# Demos

Shareable result pages and demo material, newest first. Pages on claude.ai are private until
their owner shares them (Share menu on the page).

| When (PT) | What | Link | Source runs |
| --- | --- | --- | --- |
| Sat Nov 14, 13:50 | First results: loop vs. one-shot vs. best-of-6 on 10 cases. Headline judge scores, the pendulum search tree, all cases side by side, findings | [Kinetic Sketch Autoresearch](https://claude.ai/artifact/52zhVRsQdXewQp3pxPYqPH) | `runs/20261114-131334-{one_shot,best_of_6,loop_k2_b1_c2_r2}` |

## Regenerating locally

Run outputs live in `runs/` (gitignored). To rebuild the side-by-side page from any set of runs:

```bash
uv run ksa compare runs/<one_shot> runs/<best_of_6> runs/<loop>   # writes runs/compare.html
```

## Good moments for the demo video

- **Pendulum, r0n0 → r1n0:** the first sample swings the wrong way; after seeing its own frames, the revision
  swings toward the arrow through the vertical (critic 3.00 → 4.00, final 4.25).
- **Spring–mass:** one-shot 3.17 vs. loop 4.17 under the held-out judge.
- **Sun and bolt logo intros:** build up from nothing to the finished logo, after the anchor-frame fix.
- **Windmill:** the contact-sheet aliasing story; a correct spin that the critic first called "jumpy".

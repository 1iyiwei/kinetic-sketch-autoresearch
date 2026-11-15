# Results

Curated results, committed so anyone can replay them after `git pull`. Full runs (every frame, GIF and log) stay
in the gitignored `runs/`.

Each animation is stored as its **program**, not as a video: a self-contained HTML file whose `ksaRender(t)` draws
the frame at time `t`. Because it is a pure function of time, it replays exactly the animation the judge scored, at
about 8 KB per file (a GIF of the same animation is about 180 KB). `ksa export` appends a small player that loops it.

- Open any `.html` here in a browser to watch it loop.
- Add `?t=1.5` to the URL to freeze it at t = 1.5 s.
- Each set has a `manifest.json` with the drawing's intent, category and anchor frame, and per method: the file,
  the held-out judge score (`judge`, gpt-5.4, mean of 3), the in-loop critic score (`critic`), the best score after
  each round, and the critic's first remaining issue.

| Set | Drawings | Methods | Source runs |
| --- | --- | --- | --- |
| `first-batch/` | the first 10 | `one_shot`, `best_of_6`, `loop_k2_b1_c2_r2` | `runs/20261114-131334-*` |
| `test/` | the 7 test drawings | `one_shot` (run 1 of 3), `one_shot+train-v2_select`, `loop_k2_b1_c2_r2` | `runs/v2/{oneshot-test-1,pbsel-test-1,loop-test}` |
| `complex/` | the 5 complex drawings | `one_shot` (run 1 of 3), `loop_k2_b1_c2_r2` | `runs/v2/{oneshot-complex-1,loop-complex}` |
| `pendulum-tree/` | pendulum | all 6 candidates of one loop search (`r0n0` … `r2n1`), with each one's critique | `runs/20261114-131334-loop_k2_b1_c2_r2/pendulum` |
| `anchor-fix/` | sun and bolt logo intros | `before_anchor_fix`, `after_anchor_fix` (loop, before and after the anchor-frame fix) | `runs/20261114-130842-loop…`, `runs/20261114-131334-loop…` |

Averages over several runs are in the main [README](../README.md); a set shows one run per method.

## Regenerate

```bash
uv run ksa export runs/<run A> runs/<run B> ... --name <set>           # final program per case and method
uv run ksa export runs/<run>=label ... --name <set> --cases a,b          # rename a method, choose drawings
uv run ksa export-tree runs/<run> <case> --name <set>                    # every candidate of one search
```

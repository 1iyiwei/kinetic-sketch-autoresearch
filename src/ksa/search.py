"""Search over animation programs for one case.

One function covers every method, so they share code and compute accounting:
  one-shot    k=1, rounds=0
  best-of-K   k=K, rounds=0        (equal-compute baseline: sample more, no feedback)
  loop        k, beam, children, rounds > 0
              round 0 samples k programs; each later round revises the `beam` best
              nodes into `children` new ones, steered by the critic's issues and fixes
              and by render errors. Stops early on a plateau or a near-perfect score.

Every node (program, render, critique, parent, round) is kept and written to
tree.json, so each decision in the search can be followed.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import critic, generate, llm
from .paths import relativize
from .render import Renderer


@dataclass
class Node:
    id: str
    round: int
    parent: str | None
    origin: str  # "sample" | "revise"
    ok: bool = False
    score: float = 0.0
    critique: dict = field(default_factory=dict)
    render: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class SearchConfig:
    k: int = 1
    beam: int = 1
    children: int = 2
    rounds: int = 0
    stop_at: float = 4.75  # good enough, stop early
    patience: int = 1  # rounds without improvement before stopping
    verbose: bool = False  # print the best score after each round (live demo)

    @property
    def method(self) -> str:
        if self.rounds == 0:
            return "one_shot" if self.k == 1 else f"best_of_{self.k}"
        return f"loop_k{self.k}_b{self.beam}_c{self.children}_r{self.rounds}"


async def evaluate(case, renderer: Renderer, node: Node, program: str | None, raw: str, ndir: Path,
                   png: Path, log: Path, meter: dict, method: str) -> Node:
    ndir.mkdir(parents=True, exist_ok=True)
    (ndir / "generator_raw.txt").write_text(raw)
    if program is None:
        node.error = "no ```html block in reply"
        node.critique = critic.zero_score("no program returned")
        return node
    (ndir / "program.html").write_text(program)
    rendered = await renderer.render(program, ndir / "render", duration=case["duration"])
    node.render = rendered.to_json()
    if not rendered.ok:
        node.critique = critic.zero_score("render failed: " + "; ".join(rendered.errors[:3]))
        node.error = "render failed"
    else:
        try:
            node.critique = await critic.critique(case, png, rendered.sheet, rendered.strip,
                                                  rendered.frames[-1 if case.get("anchor") == "end" else 0],
                                                  log, tags={"method": method, "node": node.id}, meter=meter)
            node.ok = True
        except llm.FatalAPIError:
            raise
        except Exception as e:  # noqa: BLE001 - a transient critic failure scores this node zero
            node.critique = critic.zero_score(f"critic call failed: {e}")
            node.error = "critic failed"
    node.score = node.critique["overall"]
    (ndir / "critique.json").write_text(json.dumps(node.critique, indent=2))
    return node


async def search(case: dict, svg: Path, png: Path, renderer: Renderer, cdir: Path, log: Path,
                 cfg: SearchConfig, playbook: str = "") -> dict:
    meter: dict = {}
    nodes: list[Node] = []
    method = cfg.method

    async def sample(i: int) -> Node:
        node = Node(id=f"r0n{i}", round=0, parent=None, origin="sample")
        try:
            program, raw = await generate.one_shot(case, svg, png, log, meter=meter,
                                                   tags={"method": method, "node": node.id}, playbook=playbook)
        except llm.FatalAPIError:
            raise
        except Exception as e:  # noqa: BLE001 - a failed call is a result
            node.error, node.critique = f"generator call failed: {e}", critic.zero_score("generator call failed")
            return node
        return await evaluate(case, renderer, node, program, raw, cdir / "nodes" / node.id, png, log, meter, method)

    async def child(parent: Node, rnd: int, j: int) -> Node:
        node = Node(id=f"r{rnd}n{j}", round=rnd, parent=parent.id, origin="revise")
        pdir = cdir / "nodes" / parent.id
        program_path = pdir / "program.html"
        if not program_path.exists():  # nothing to revise: resample instead
            node.origin = "sample"
            try:
                program, raw = await generate.one_shot(case, svg, png, log, meter=meter,
                                                       tags={"method": method, "node": node.id}, playbook=playbook)
            except llm.FatalAPIError:
                raise
            except Exception as e:  # noqa: BLE001
                node.error, node.critique = f"generator call failed: {e}", critic.zero_score("generator call failed")
                return node
        else:
            sheet = Path(parent.render["sheet"]) if parent.render.get("sheet") else None
            strip = Path(parent.render["strip"]) if parent.render.get("strip") else None
            try:
                program, raw = await generate.revise(
                    case, svg, png, program_path.read_text(), parent.critique,
                    parent.render.get("errors", []), sheet, strip, log, meter=meter,
                    tags={"method": method, "node": node.id, "parent": parent.id}, playbook=playbook)
            except llm.FatalAPIError:
                raise
            except Exception as e:  # noqa: BLE001
                node.error, node.critique = f"generator call failed: {e}", critic.zero_score("generator call failed")
                return node
        return await evaluate(case, renderer, node, program, raw, cdir / "nodes" / node.id, png, log, meter, method)

    nodes += await asyncio.gather(*(sample(i) for i in range(cfg.k)))
    best = max(nodes, key=lambda n: n.score)
    history = [best.score]
    if cfg.verbose:
        print(f"    round 0: {len(nodes)} samples, best {best.score:.2f} ({best.id})", flush=True)
    stale = 0
    for rnd in range(1, cfg.rounds + 1):
        if best.score >= cfg.stop_at or stale >= cfg.patience:
            break
        parents = sorted(nodes, key=lambda n: n.score, reverse=True)[: cfg.beam]
        jobs = [child(p, rnd, bi * cfg.children + c) for bi, p in enumerate(parents) for c in range(cfg.children)]
        nodes += await asyncio.gather(*jobs)
        new_best = max(nodes, key=lambda n: n.score)
        stale = 0 if new_best.score > best.score else stale + 1
        best = new_best
        history.append(best.score)
        if cfg.verbose:
            print(f"    round {rnd}: revised {len(jobs)}, best {best.score:.2f} ({best.id})", flush=True)

    tree = {"case": case["id"], "method": method, "config": asdict(cfg), "best": best.id,
            "best_score_by_round": history, "meter": meter, "nodes": [asdict(n) for n in nodes]}
    (cdir / "tree.json").write_text(json.dumps(relativize(tree, cdir.parent), indent=2))
    return {"case": case["id"], "category": case["category"], "method": method, "best_node": best.id,
            "critique": best.critique, "render": best.render, "best_score_by_round": history,
            "n_nodes": len(nodes), "meter": meter, "program": str(cdir / "nodes" / best.id / "program.html")}

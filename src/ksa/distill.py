"""Distill the research loop into an open model with Tinker (expert iteration).

  # 1. teacher data: run the loop on the training split
  uv run python benchmark/make_train_cases.py
  uv run ksa run --method loop --cases-file benchmark/train/cases.json
  # 2. export the loop's best programs as chat SFT examples (benchmark cases are always excluded)
  uv run python -m ksa.distill export runs/<train-run> [...] --out data/sft_r1.jsonl
  # 3. LoRA SFT on Tinker; prints the sampler checkpoint path
  uv run python -m ksa.distill train data/sft_r1.jsonl --name r1
  # 4. the student as generator, on the held-out benchmark (one-shot or inside the loop)
  KSA_GEN_MODEL=tinker://... uv run ksa run --method oneshot
  # round 2: KSA_GEN_MODEL=tinker://... on the training split, export, train again

TINKER_API_KEY is read from the environment by the Tinker SDK; it is never logged here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from . import generate, llm

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark" / "cases" / "cases.json"


def held_out_ids() -> set[str]:
    return {c["id"] for c in json.loads(BENCHMARK.read_text())}


def run_cases(run_dir: Path, meta: dict) -> dict[str, dict]:
    path = Path(meta.get("cases_file") or BENCHMARK)
    cases = json.loads(path.read_text())
    for c in cases:
        c["svg"] = str((path.parent / c["svg"]).resolve())
    return {c["id"]: c for c in cases}


def example(case: dict, program: str) -> dict:
    svg = Path(case["svg"]).read_text()
    return {"case": case["id"], "messages": [
        {"role": "system", "content": generate.SYSTEM},
        {"role": "user", "content": generate.build_prompt(case, svg)},
        {"role": "assistant", "content": f"```html\n{program.strip()}\n```"},
    ]}


def export(args):
    blocked = held_out_ids()
    rows, skipped = [], {"held_out": 0, "low_score": 0, "missing": 0}
    for rd in map(Path, args.run_dirs):
        data = json.loads((rd / "results.json").read_text())
        cases = run_cases(rd, data["meta"])
        judged = None
        if args.judge:
            jf = json.loads((rd / f"judge-{llm.slug(args.judge)}.json").read_text())
            judged = {c["case"]: sum(c["overall"]) / len(c["overall"]) for c in jf["per_case"]}
        for rec in data["results"]:
            cid = rec["case"]
            if cid in blocked:
                skipped["held_out"] += 1
                continue
            if judged is not None:  # select by the run's independent judge, best program only
                score = judged.get(cid)
                prog = Path(rec.get("program") or "")
                if score is None or not prog.exists():
                    skipped["missing"] += 1
                elif score < args.min_score:
                    skipped["low_score"] += 1
                else:
                    ex = example(cases[cid], prog.read_text())
                    ex.update(score=score, source=str(prog))
                    rows.append(ex)
                continue
            # every node at or above the bar (best first), capped per case
            nodes = []
            for crit in (rd / cid / "nodes").glob("*/critique.json"):
                score = json.loads(crit.read_text()).get("overall", 0.0)
                prog = crit.parent / "program.html"
                if prog.exists():
                    nodes.append((score, prog))
            nodes.sort(key=lambda x: x[0], reverse=True)
            keep = [(s, p) for s, p in nodes if s >= args.min_score][: args.per_case]
            if not nodes:
                skipped["missing"] += 1
            elif not keep:
                skipped["low_score"] += 1
            for s, p in keep:
                ex = example(cases[cid], p.read_text())
                ex.update(score=s, source=str(p.relative_to(rd.parent)))
                rows.append(ex)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    n_cases = len({r["case"] for r in rows})
    print(f"wrote {len(rows)} examples from {n_cases} cases -> {out}  skipped {skipped}")


def make_datum(tokenizer, messages: list[dict]):
    import tinker
    prompt = llm.chat_tokens(tokenizer, messages[:-1], True)
    full = llm.chat_tokens(tokenizer, messages, False)
    if full[: len(prompt)] != prompt:  # template re-renders the prefix differently: fall back to text split
        raise ValueError("chat template prefix mismatch")
    weights = [0.0] * len(prompt) + [1.0] * (len(full) - len(prompt))
    return tinker.Datum(model_input=tinker.ModelInput.from_ints(full[:-1]),
                        loss_fn_inputs={"target_tokens": full[1:], "weights": weights[1:]}), len(full)


async def train(args):
    import tinker
    rows = [json.loads(line) for line in Path(args.data).read_text().splitlines() if line.strip()]
    leaked = {r["case"] for r in rows} & held_out_ids()
    if leaked:
        raise SystemExit(f"refusing to train: held-out cases in data: {sorted(leaked)}")
    def make():  # the SDK's client constructors are sync-only
        tc = tinker.ServiceClient().create_lora_training_client(base_model=args.base_model, rank=args.rank)
        tc = tc.result() if hasattr(tc, "result") else tc
        return tc, tc.get_tokenizer()

    tc, tok = await asyncio.to_thread(make)
    data, lengths = [], []
    for r in rows:
        try:
            d, n = make_datum(tok, r["messages"])
        except ValueError as e:
            print(f"  skip {r['case']}: {e}")
            continue
        if n <= args.max_len:
            data.append(d)
            lengths.append(n)
    if not data:
        raise SystemExit("no usable examples")
    print(f"{len(data)} examples, mean {sum(lengths) / len(lengths):.0f} tokens, base {args.base_model}")
    out_dir = ROOT / "runs" / f'distill-{time.strftime("%Y%m%d-%H%M%S")}-{args.name}'
    out_dir.mkdir(parents=True)
    log = (out_dir / "train_log.jsonl").open("a")
    rng = random.Random(args.seed)
    steps_per_epoch = max(1, len(data) // args.batch)
    total, step, ckpts = steps_per_epoch * args.epochs, 0, []
    for epoch in range(args.epochs):
        rng.shuffle(data)
        for b in range(steps_per_epoch):
            batch = data[b * args.batch:(b + 1) * args.batch]
            lr = args.lr * (1 - step / total)  # linear decay
            fb = tc.forward_backward(batch, "cross_entropy")
            opt = tc.optim_step(tinker.AdamParams(learning_rate=lr))
            res = await fb
            await opt
            lp = [x for o in res.loss_fn_outputs for x in o["logprobs"].tolist()]
            w = [x for d in batch for x in d.loss_fn_inputs["weights"].tolist()]
            loss = -sum(a * c for a, c in zip(lp, w)) / max(sum(w), 1.0)
            step += 1
            log.write(json.dumps({"step": step, "epoch": epoch, "lr": lr, "loss": loss}) + "\n")
            log.flush()
            print(f"  epoch {epoch} step {step}/{total} loss {loss:.4f}", flush=True)
        ck = await tc.save_weights_for_sampler(name=f"{args.name}-e{epoch}")
        ckpts.append({"epoch": epoch, "path": ck.path})
        print(f"  checkpoint: {ck.path}", flush=True)
    meta = {"base_model": args.base_model, "rank": args.rank, "lr": args.lr, "epochs": args.epochs,
            "batch": args.batch, "n_examples": len(data), "data": str(args.data), "checkpoints": ckpts}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"done -> {out_dir}\nuse: KSA_GEN_MODEL={ckpts[-1]['path']} uv run ksa run --method oneshot")


def motion(frames: list[str]) -> float:
    """Mean absolute pixel change between consecutive frames (0-1); ~0 means nothing moves."""
    from PIL import Image, ImageChops, ImageStat
    if len(frames) < 2:
        return 0.0
    ims = [Image.open(f).convert("L").resize((128, 128)) for f in frames]
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean[0] for a, b in zip(ims, ims[1:])) / (255 * (len(ims) - 1))


def report(args):
    """One comparison table (held-out judge, render validity, generator cost) across runs."""
    rows = []
    for rd in map(Path, args.run_dirs):
        data = json.loads((rd / "results.json").read_text())
        meta, res = data["meta"], data["results"]
        jf = rd / f"judge-{llm.slug(args.judge)}.json"
        judge = json.loads(jf.read_text())["mean"] if jf.exists() else None
        critic = sum(r["critique"]["overall"] for r in res) / len(res)
        valid = sum(bool(r.get("render", {}).get("ok")) for r in res) / len(res)
        gen = [r.get("meter", {}).get("generator", {}) for r in res]
        toks = sum(g.get("input_tokens", 0) + g.get("output_tokens", 0) for g in gen) / len(res)
        allt = sum(sum(m["input_tokens"] + m["output_tokens"] for m in r.get("meter", {}).values()) for r in res) / len(res)
        secs = sum(r.get("seconds", 0) for r in res) / len(res)
        f1 = sum(r["critique"].get("measured", {}).get("fidelity_f1", 0) for r in res) / len(res)
        moving = sum(motion(r["render"].get("frames", [])) > args.motion_min
                     for r in res if r.get("render", {}).get("ok")) / len(res)
        model = meta.get("gen_model", "?").replace("sampler_weights/", "")[-40:]
        rows.append(f"| {rd.name} | {model} | {meta['method']} | "
                    f"{'%.2f' % judge if judge is not None else '-'} | {critic:.2f} | {valid:.0%} | {f1:.2f} | {moving:.0%} | "
                    f"{toks / 1000:.0f}K | {allt / 1000:.0f}K | {secs:.0f}s |")
    table = "\n".join([f"| run | generator | method | judge ({args.judge}) | critic | valid renders | "
                        "anchor F1 | moving | gen tokens/case | all tokens/case | sec/case |",
                        "|---|---|---|---|---|---|---|---|---|---|---|", *rows])
    print(table)
    if args.out:
        Path(args.out).write_text(table + "\n")


def main():
    p = argparse.ArgumentParser(prog="ksa.distill")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="SFT jsonl from loop runs on the training split")
    e.add_argument("run_dirs", nargs="+")
    e.add_argument("--out", default=str(ROOT / "data" / "sft.jsonl"))
    e.add_argument("--min-score", type=float, default=3.75)
    e.add_argument("--per-case", type=int, default=2, help="max programs kept per case")
    e.add_argument("--judge", help="select each case's best program by this judge's judge-<model>.json instead of critic scores")
    t = sub.add_parser("train", help="LoRA SFT on Tinker")
    t.add_argument("data")
    t.add_argument("--base-model", default=llm.TINKER_BASE)
    t.add_argument("--rank", type=int, default=32)
    t.add_argument("--lr", type=float, default=2e-4)
    t.add_argument("--epochs", type=int, default=3)
    t.add_argument("--batch", type=int, default=8)
    t.add_argument("--max-len", type=int, default=24000)
    t.add_argument("--name", default="sft")
    t.add_argument("--seed", type=int, default=0, help="data shuffle seed")
    r = sub.add_parser("report", help="compare runs: judge score, validity, cost")
    r.add_argument("run_dirs", nargs="+")
    r.add_argument("--judge", default="gpt-5.4")
    r.add_argument("--out")
    r.add_argument("--motion-min", type=float, default=0.001)
    args = p.parse_args()
    if args.cmd == "export":
        export(args)
    elif args.cmd == "report":
        report(args)
    else:
        asyncio.run(train(args))


if __name__ == "__main__":
    main()

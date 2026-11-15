# Submission

## Project title

Kinetic Sketch Autoresearch

## Description

A model that writes animation code can't see its mistakes. Ours renders what it wrote, watches it, fixes it, and tests whether the lessons carry to new drawings.

Sketches, textbook diagrams, cartoons and logos in; stylized animation programs out.

Used OpenAI and Tinker-hosted models to create an autoresearch loop, with Exa web search inside the loop.

## Track

1 Build your own autoresearch framework

## Challenges (pick any)

[x] Exa
Build a research agent that uses Exa to find what it doesn’t already know. Open to every track and any research problem. The strongest projects do something they couldn’t do from model knowledge alone: find the paper that changes the plan, pull in data published last week, or check a claim against real sources. At least one Exa call (search, contents, find similar, answer, research or Websets) must run in the project’s main loop, and the demo should show what the system found through Exa and how it used it.

Our claim: Exa runs inside the self-correction loop. The critic can tell that a motion is wrong ("the pendulum swings the wrong way", "the flag doesn't wave") but not how the thing really moves. With `--exa`, before each revision the loop searches the web for the drawing's intended motion, steered by the critic's top issue, and gives the reviser short excerpts with their sources (for a pendulum: Wikipedia and physics tutorials on how gravity pulls the bob back and it overshoots). Every search, its sources and which revision used it are logged (`exa.jsonl`, `tree.json`), and the sketch pad lists the sources live during a run. Exa also supplies inputs: "Find a drawing" searches open-licence SVG sites (SVG Repo, Wikimedia Commons, Openclipart) for a text description, and the chosen drawing is cleaned and animated. Code: `src/ksa/exa.py`.

[] past.dev
Build a shared memory layer for a multi-agent setup or swarm using past.dev, and prove better accuracy, latency gains and cost reduction than the common existing approaches.

[] Modal
Best use of Modal: training, inference, or running large numbers of experiments and agent sandboxes in parallel.

## Github URL
https://github.com/1iyiwei/kinetic-sketch-autoresearch

## Video link
https://youtu.be/q5HoxP6mZOM
# Phase 3: VLM integration (single-step decisions)

> **Status**: STUB. Expand when Phase 2 is done. The biggest open question
> below — local vs API VLM — should be resolved before this phase starts.

## Goal

Replace the keyboard teleop with a VLM-based decision node. Given a
natural-language task and the latest camera frame, the VLM outputs a
structured JSON action. No memory between calls — each decision is
independent. This is the "make the loop close" phase, where the system
becomes autonomous (badly, at first).

## Non-goals

- No memory or history across decisions (Phase 4).
- No search-specific behavior or termination logic (Phase 4).
- No fine-tuning. Off-the-shelf VLM only.
- No latency optimization below ~2s per decision. Slow but working is the
  target.

## Deliverables (rough)

1. ROS 2 package `crawler_vlm`:
   - `vlm_node.py`: subscribes to camera + task, publishes `/robot_0/cmd`.
   - Backend abstraction so we can swap between API and local VLM.
   - Mock backend that returns canned responses for offline testing.
2. Prompt templates in `workstation/src/crawler_vlm/prompts/`:
   - `single_step.txt` — the main system prompt.
   - Iterated on, version-controlled.
3. JSON schema for VLM output, enforced via Pydantic. Malformed output →
   "stop" + log warning. Never crash on bad JSON.
4. Bag-replay tests: feed 3 recorded scenarios, verify the VLM produces
   sensible actions for each (manual review).
5. New launch file `vlm_drive.launch.py` that swaps teleop for VLM.

## Design notes (to be expanded)

- Decision rate: ~0.5-1 Hz. Safety loop on Pi handles fast reactive stop.
- Task input: probably via ROS parameter at launch time. Could be a topic
  later if we want to change tasks mid-run.
- Image preprocessing: most VLMs prefer ~448 or 384 px square inputs.
  Resize/crop before sending. Don't waste tokens on margins.
- The VLM node should log its reasoning, not just the action. We want to
  see "why" for debugging.

## Open questions

1. **Local VLM vs API.** Biggest open question.
   - **Local options**: Qwen2.5-VL-7B via vLLM (good), InternVL3 small,
     Llama 3.2 Vision. RTX 5090 handles 7B easily, can probably do
     larger quantized.
   - **API options**: Claude (latest Sonnet/Opus), GPT-4o, Gemini 2.5.
     Faster iteration, no setup, costs ~$0.01-0.05 per decision.
   - **My lean**: start with API (fast iteration, week 1), switch to
     local once the prompt and JSON schema are solid.
2. **Action space.** Stick with `forward / turn_left / turn_right / stop`?
   Or add `forward_small`, `turn_45`, etc. for finer control?
   More actions = more VLM confusion. Start minimal.
3. **What does "stop" mean to the VLM?** Task complete? Give up?
   Need-more-info? Probably need separate fields: `action` + `status`
   (`continuing` / `target_found` / `cannot_proceed`).
4. **How is the task delivered to the VLM?** Just paste into the system
   prompt? A separate user message with the image? Test both.

## Working style

Iterative and incremental:

1. Mock VLM returning hardcoded "forward" — verify ROS wiring.
2. Real VLM, simplest possible prompt, no error handling.
3. Add JSON schema validation. Bag-replay test with one scenario.
4. Prompt iteration against bag-replay until output is consistently
   sensible.
5. Hardware test in a real room.

Stop after each step. Bag-replay is the workhorse here — don't run the
robot for every prompt tweak.

## Testing plan

- **Mock test**: verify ROS topic plumbing with hardcoded mock VLM.
- **Bag replay**:
  - Scenario 1: empty room, task "find the backpack". VLM should
    suggest turning/exploring.
  - Scenario 2: backpack visible, task "find the backpack". VLM should
    suggest approach.
  - Scenario 3: wall directly ahead, task "find the backpack". VLM
    should suggest turning.
- **JSON robustness**: deliberately break the prompt, verify the node
  falls back to "stop" cleanly.
- **Hardware**: real robot in a real room, supervised. Task: "find the
  blue book." Run for 2-3 minutes, observe behavior.

## Scope

Medium-large. A long weekend if the API path goes smoothly, longer if
local VLM setup or prompt engineering eats time. Plan for prompt
engineering to take *most* of the calendar time — the wiring is easy,
making the VLM produce reliable JSON is the hard part.

## Definition of done

- VLM node consumes camera + task, produces structured JSON commands.
- Bag-replay scenarios produce sensible actions in manual review.
- Robot can be put in a room with a target object and *something
  reasonable* happens — even if it's not yet a full search. Forward
  motion toward visible targets, exploration when nothing visible,
  not crashing into walls.

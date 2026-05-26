# Phase 5: Demo polish + writeup

> **Status**: STUB. Expand when Phase 4 is done. This phase is the
> difference between a working project and a portfolio piece.

## Goal

Take a working search system and turn it into a thing other people can
*see* and *understand*. The technical work is done; this phase is about
recording, writing, and presenting. Specifically: a video, a public
GitHub repo, and a writeup that's submission-ready for grad school
materials.

## Non-goals

- No major new behaviors. If something doesn't work by now, scope it
  out rather than building it in.
- No public release of the SunFounder modifications or anything that
  would create maintenance burden.

## Deliverables

1. **Demo video** (60-90 seconds):
   - Setup shot: room, robot, target object.
   - Operator command (typed in terminal, visible on screen).
   - Robot searching: visible "looking around" behavior.
   - Moment of finding the target.
   - Final natural-language report.
   - Optional: top-down view via phone tripod, picture-in-picture.
2. **Cleaned GitHub repo**:
   - Public, with full README.
   - Architecture diagram (TikZ or draw.io export).
   - SortBots framing paragraph.
   - Links to demo video, writeup, and (if applicable) the conference
     paper.
3. **Project writeup** (4-8 pages, PDF):
   - Motivation and framing (SortBots precursor).
   - System design.
   - VLM prompt design notes.
   - What worked, what didn't, what I'd do differently.
   - Multi-robot extension sketch.
4. **Operator UI** (optional, if time):
   - Simple terminal UI showing the camera feed, current task, VLM
     reasoning, and current action.
   - Helps the demo video read better than a wall of logs.
5. **README updates** across `pi/`, `workstation/`, `docs/`.

## Design notes (to be expanded)

- The demo video is the single highest-leverage artifact. Plan it
  carefully: storyboard before recording.
- The writeup matters more than the code quality. Hiring committees /
  admissions read the writeup; they skim the code.
- Failure cases in the video > flawless runs. "Here's what happens
  when it can't find the target" shows maturity.

## Open questions

- Operator UI: build it, or skip and just use terminal output?
- Should the video include voiceover, or rely on text overlays?
- Where does the writeup live? GitHub README? PDF in the repo?
  Personal website? Probably all three, slightly adapted.

## Working style

Slower, more deliberate. This phase is not about shipping code, it's
about polish. Treat each deliverable as a small project of its own.

Write the writeup *while* recording the demo, not after. The act of
explaining the system in writing will reveal gaps in the demo, and
vice versa.

## Testing plan

- Show the demo video to one technical friend and one non-technical
  friend. If either is confused by anything in the first 15 seconds,
  re-edit.
- Have someone unfamiliar with the project read the README and try to
  understand what the project is, in under 60 seconds. If they can't,
  rewrite the README opener.

## Scope

Smaller in code, larger in calendar time. Plan for video re-shoots and
writeup revisions. The "definition of done" is harder to nail here
because it's qualitative.

## Definition of done

- Video is on YouTube/Vimeo, embedded in repo README.
- Writeup is committed as PDF in `docs/writeup.pdf`.
- Repo is public, with clear README and architecture diagram.
- I can point to all of this in an MS application's portfolio section
  without flinching.

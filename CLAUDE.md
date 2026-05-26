# Project: Pi-Crawler VLM Search

## Overview

A VLM-driven autonomous search quadruped. The operator gives a natural-
language task ("find the blue backpack"); a VLM on the workstation
reasons over the camera stream and issues discrete movement commands;
the robot executes them with a local safety layer.

Framed as the single-robot precursor to my SortBots capstone project
(multi-robot decentralized warehouse exploration). Architecture
decisions should be consistent with later extension to N robots.

## Hardware

- **Workstation**: Ubuntu 24.04, GTX 4070.
  Runs all heavy compute (VLM inference, perception, planning).
  Hostname: andre. IP: 192.168.1.187.
- **Robot**: SunFounder Pi-Crawler quadruped. Raspberry Pi (1GB RAM),
  RPi camera module, ultrasonic sensor. SunFounder's stock Python
  library is installed per
  https://docs.sunfounder.com/projects/pi-crawler/en/latest/python/play_with_python.html. All of the demo scripts on that doc site work properly
  Reachable via `ssh pi@raspberrypi.local`. IP: 192.168.1.19.
- **Network**: Pi on WiFi, workstation on wired Ethernet or wireless, same LAN.

## Architecture

- Pi is a thin client: streams sensors up, executes commands down.
  TODO: Explore if the PI can run a lightweight ROS node (runs an older raspian distro, Bullseye). 
- Workstation runs ROS 2 Jazzy.
- Telemetry (camera, ultrasonic): UDP, drop stale frames cheerfully.
- Commands: TCP, ensure delivery.
- Safety: fast loop on the Pi runs at 10+ Hz, handles ultrasonic
  emergency stop and command-timeout fallback (stop if no command
  received in 1 second). Safety loop is independent of workstation
  state — robot must fail safe if WiFi drops.
- Topics use namespaced format (`/robot_0/camera/image`, etc.) for
  multi-robot extensibility later.

## Project structure

- `pi/` — code that runs on the Raspberry Pi. Lightweight Python only.
- `workstation/` — ROS 2 packages and workstation-side Python.
  Colcon workspace under `workstation/src/`.
- `docs/` — design notes, architecture diagrams, writeup drafts.
- `scripts/` — one-off helpers (deployment, testing, log analysis).

## Conventions

- ROS 2 Jazzy idioms: rclpy, Python launch files, ament_python builds.
- Type hints on all new Python code.
- Black for formatting, ruff for linting.
- Commit messages: conventional commits style (feat:, fix:, docs:, etc.), ensure claude is not mentioned in the commit message, and keep claude artifcats in the gitignore (may need to initially update this)

## Hard rules

- DO NOT add VLM, perception, or planning code in Phase 1.
  Resist scaffolding for later phases.
- DO NOT introduce dependencies on the Pi beyond stdlib, picamera2,
  opencv-python, numpy, and the SunFounder library, without asking.
- DO NOT refactor the messaging layer without flagging it explicitly
  in the response.
- The safety loop on the Pi must never depend on workstation reachability.

## Current phase: Phase 1 — messaging foundation

Goal: reliable Pi ↔ workstation messaging end-to-end, with a teleop
node on the workstation that can drive the robot by keyboard. The sunfounder docs linked above should include an example (local) teleoperation script.

No VLM,
no autonomy, no perception beyond raw frame forwarding. We are still early 

## Phase roadmap (for context, not for this session)

1. Messaging foundation (current).
2. Pi-side safety loop hardening.
3. VLM integration (single-step decisions, no memory).
4. Search behavior (text memory, approach-and-confirm).
5. Demo polish (logging, operator UI, recording setup).
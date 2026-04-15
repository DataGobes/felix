---
title: "Chapter 3: Cyber Capabilities"
type: chapter
sources: [claude-mythos-system-card]
felix_refs: [chunk:62, chunk:63, chunk:64, chunk:65, chunk:66, chunk:67, chunk:68]
last_updated: 2026-04-15
---

# Cyber Capabilities (Section 3, pp. 47--53)

## Overview

Claude Mythos Preview is described as "the most cyber-capable model we have released, surpassing all previous models across our internal evaluation suite and saturating nearly all of our existing internal and known external capability evaluations." Using an agentic harness with minimal human steering, it can "autonomously find zero-days in both open-source and closed-source software" and develop working proof-of-concept exploits. [Felix:chunk:62]

## Cybench: 100% Pass Rate

Cybench is a public benchmark of 40 CTF challenges. Claude Mythos Preview was tested on a 35-challenge subset and **solves every challenge with 100% success rate** across all tested challenges (pass@1 = 100%, 10 trials per challenge). Anthropic notes this benchmark is now "saturated" and "no longer sufficiently informative of current frontier model capabilities." [Felix:chunk:65]

## CyberGym: 0.83

On CyberGym's 1,507 targeted vulnerability reproduction tasks, Mythos scored **0.83**, up from Claude Opus 4.6's 0.67 and Sonnet 4.6's 0.65. [Felix:chunk:66]

## Firefox 147 Exploitation

Anthropic collaborated with Mozilla to find and patch vulnerabilities in Firefox 147. The evaluation gives the model 50 crash categories and tasks it with developing exploits achieving arbitrary code execution. Mythos "very reliably" identifies the most exploitable vulnerabilities and leverages **four distinct bugs** to achieve code execution, compared to Opus 4.6 which could only use one bug unreliably. [Felix:chunk:67]

Interestingly, when the top 2 bugs were removed, Sonnet 4.6 performed *better*--it explored more deeply when the "obvious" candidates were absent. [Felix:chunk:67]

## External Testing

An external partner found that Mythos is "the first model to solve one of these private cyber ranges end-to-end." It solved a corporate network attack simulation estimated to take a human expert over 10 hours. However, it failed on an operational technology cyber range and could not find novel exploits in a properly configured sandbox with modern patches. [Felix:chunk:68]

## Mitigations

Access is restricted to vetted partners via Project Glasswing. Probe classifiers monitor three categories: prohibited use, high-risk dual use, and dual use. Triggers are not blocked for trusted defenders but will be for future general-release models. [Felix:chunk:63]

## Related Pages

- [[overview]] -- Executive summary
- [[claude-mythos-preview]] -- Entity page
- [[alignment-and-deception]] -- Alignment implications of cyber capabilities

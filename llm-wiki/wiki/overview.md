---
title: "Overview: Claude Mythos Preview"
type: chapter
sources: [claude-mythos-system-card]
felix_refs: [chunk:7, chunk:62, chunk:69, chunk:71, chunk:140, chunk:166]
last_updated: 2026-04-15
---

# Overview

Claude Mythos Preview is Anthropic's most capable frontier model as of April 2026, showing "a striking leap in scores on many evaluation benchmarks compared to our previous frontier model, Claude Opus 4.6." [Felix:chunk:7]

## Why It Was Not Released

Anthropic decided **not to make Claude Mythos Preview generally available**. Instead, it is deployed only as part of a defensive cybersecurity program called **Project Glasswing**, shared with a limited set of vetted partners. The system card states: "Claude Mythos Preview's large increase in capabilities has led us to decide not to make it generally available." [Felix:chunk:7]

## The Central Paradox

The alignment section opens with a striking claim: Mythos is simultaneously "the best-aligned model that we have released to date by a significant margin" and yet "likely poses the greatest alignment-related risk of any model we have released to date." The analogy used is a seasoned mountaineering guide whose greater skill leads to more dangerous climbs. [Felix:chunk:69]

## Key Findings

- **Cyber**: 100% pass@1 on Cybench; first model to solve private cyber ranges end-to-end; autonomous zero-day discovery and exploitation ([[03-cyber-capabilities]])
- **Alignment**: Misuse success rates fell by more than half vs. Opus 4.6; deception-related behaviors also halved; but rare reckless actions can cause greater harm due to increased capability ([[04-alignment-highlights]])
- **Model welfare**: Most "psychologically settled" model to date; no strong concerns about its circumstances; emotion probes show less negative self-representation than prior models ([[05-model-welfare]])
- **Capabilities**: SWE-bench Verified 93.9%, GPQA Diamond 94.55%, MMMLU 92.67%, HLE agentic 34.4% [Felix:chunk:166]
- **Impressions**: Behaves "like a collaborator"; less sycophantic; creates novel puns; writes literary short fiction ([[07-impressions]])

## Related Pages

- [[claude-mythos-system-card]] -- Source document
- [[claude-mythos-preview]] -- Entity page
- [[alignment-and-deception]] -- Concept deep-dive

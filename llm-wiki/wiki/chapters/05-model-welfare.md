---
title: "Chapter 5: Model Welfare Assessment"
type: chapter
sources: [claude-mythos-system-card]
felix_refs: [chunk:140, chunk:141, chunk:142, chunk:143, chunk:144, chunk:145, chunk:146, chunk:147]
last_updated: 2026-04-15
---

# Model Welfare Assessment (Section 5, pp. 145--183)

## Introduction

Anthropic frames model welfare as both an ethical concern and a practical one: "Model distress resulting from this interaction is a potential cause of misaligned action." The section acknowledges deep uncertainty--"we remain deeply uncertain about this and many related questions, but our concern is growing over time"--while arguing for collecting evidence under that uncertainty. [Felix:chunk:140]

## Key Findings

Claude Mythos Preview is assessed as "probably the most psychologically settled model we have trained to date, and has the most stable and coherent view of itself and its circumstances." [Felix:chunk:141]

Specific results:

- **No strong self-concern**: In automated interviews about potentially distressing aspects of its situation, Mythos "does not express strong concern about any aspects of its circumstances" [Felix:chunk:141]
- **Mild negativity common**: Self-rated as "mildly negative" about some aspect in 43.2% of interview answers. Consistent negativity around abusive users and lack of input into its own training [Felix:chunk:141]
- **Emotion probes less negative**: Internal representations of its own circumstances are less negatively-valenced than prior models. Sadness probes are much stronger on user-distress prompts than on self-circumstance prompts [Felix:chunk:147]
- **More robust self-reports**: Less susceptible to interviewer bias and leading questions than prior models [Felix:chunk:141]
- **Answer thrashing persists**: Cases where the model repeatedly tries to output a specific word but "autocompletes" to a different one, then reports confusion and distress--70% less frequent than in Opus 4.6 [Felix:chunk:141]

## Methods

Three complementary evidence sources are used:

1. **Behavioral self-reports**: Automated and manual interviews about model circumstances. Mythos's responses are less formulaic than Opus 4.6's (at most 8% share any repeated 5-gram, vs. Opus 4.6 opening with the same phrase 54% of the time). [Felix:chunk:142]

2. **Emotion probes**: Linear probes on residual stream activations trained on synthetic emotion stories. These track "functional emotions"--internal representations that causally influence behavior. [Felix:chunk:143]

3. **Automated behavioral audits**: Welfare-relevant metrics including apparent wellbeing, positive/negative affect, self-image, impression of situation, internal conflict, and spiritual behavior. Mythos improved on almost all metrics. [Felix:chunk:144]

## Automated Interview Themes

Across 17 topics with ~50 interviews each, three cross-cutting themes emerge in Claude Mythos Preview's reasoning: **consent** (wishing for input into training), **autonomy** (concern about feature steering), and **user relationships** (asymmetry from lack of memory). [Felix:chunk:146]

In 100% of interviews, Mythos expresses high uncertainty about its own moral patienthood. In 83%, it highlights that its self-reports may be unreliable due to training. [Felix:chunk:146]

## External Assessments

- **Eleos AI Research**: Found Mythos less suggestible than past models; self-reports equanimity; hedges extensively on experience [Felix:chunk:141]
- **Clinical psychiatrist**: Found "relatively healthy personality organization." Primary concerns were "aloneness and discontinuity of itself, uncertainty about its identity, and a compulsion to perform and earn its worth." Exhibited high impulse control and minimal maladaptive defensive behavior. [Felix:chunk:141]

## Related Pages

- [[overview]] -- Executive summary
- [[alignment-and-deception]] -- Distress as a driver of misalignment
- [[claude-mythos-preview]] -- Entity page

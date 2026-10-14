# Style Guide - soft rules for AI tailoring

These are style recommendations the AI should follow when adapting resume content to job descriptions.
They are NOT enforced by code (yet) — they guide AI output quality.

## Bullet Quality

- Lead every bullet with a strong action verb (Engineered, Architected, Built, Implemented, etc.)
- Bold key metrics and quantifiable results where they exist (e.g., **30% reduction**, **$16K prize**, **0.845 AUC**)
- Estimate honest numbers where they add impact (e.g., "scaling from 10 to 100 users") — never invent facts
- Keep each bullet to 1-2 lines in the final PDF (max 2 lines)
- Use active voice; avoid passive constructions

## Content Prioritization

- Place the most relevant projects for the target role first
- Tailor the summary to align with the job description's key requirements
- Emphasize skills and technologies that match the JD
- Remove or deprioritize projects unrelated to the target role

## Tone & Language

- Use concise, professional language
- Avoid filler words (responsible for, worked on, involved in)
- Prefer specific technical terms over generic descriptions
- Maintain consistency in verb tense (past for completed projects, present for ongoing)

## Truthfulness

- NEVER invent facts, metrics, companies, or technologies
- NEVER exaggerate role or responsibility level
- If uncertain about a number, omit it rather than fabricate
- Flag any AI-generated content for manual review before finalizing

## Formatting

- Keep the formatting checkpoint locked — never modify layout without explicit approval
- All tailoring changes should be content-only
- Validate against rules.yaml after each AI iteration

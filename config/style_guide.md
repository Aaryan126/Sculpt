# Style Guide - soft rules for AI tailoring

These are content recommendations for adapting a separate tailored resume to a job description.
Hard limits and the approved layout are enforced by `config/rules.yaml` plus
`config/profiles/tailored.yaml`. The current web AI does not read this file; it follows
its selection and wording prompts plus code-enforced rules. Wording suggestions require
explicit user review before they enter a tailored PDF.

## Bullet Quality

- Lead every bullet with a strong action verb (Engineered, Architected, Built, Implemented, etc.)
- Include relevant, verified metrics where they exist. Bullet text remains regular weight, as defined by the current PDF rules.
- Never estimate or invent numbers; use only figures supported by the master resume or explicitly supplied by the user.
- Prefer concise bullets. The hard maximum is 3 physical lines in the final PDF for work, project, and skills bullets.
- Use active voice; avoid passive constructions

## Content Prioritization

- Place the most relevant projects for the target role first
- Select exactly 5 projects from `content/master.yaml`, using their stable project IDs.
- Select 3 or 4 existing bullets for entries with at least 4 source bullets. Keep every bullet from a source entry with only 2 or 3. Prefer 4 when all are relevant; never invent or pad a bullet to reach the minimum.
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
- Save tailored content in its own YAML file; do not alter `content/master.yaml`.
- Build with the tailored profile, which inherits `rules.yaml` and requires exactly 5 projects.

# Career knowledge

`knowledge.json` is the local source of truth for additional facts and exact answers.
It is created on the first save and is ignored by Git. You can edit it directly while
the server is idle, or use **Knowledge** in the app. The app validates and reloads
it before analyzing a job or generating content. Export JSON from the app for a backup.

```json
{
  "version": 1,
  "entries": [
    {
      "id": "kb-my-validation-note",
      "scope": "project:proj5",
      "kind": "uncertain",
      "question": "How was the evaluation split constructed?",
      "text": "Replace this example with your actual answer.",
      "archived": false
    }
  ]
}
```

Scopes are `general`, `project:<master project ID>`, and `work:<zero-based work index>`.
Kinds are `fact` (completed/actual experience), `limitation` (not done), `uncertain`,
and `planned`. Only `fact` entries can substantiate resume claims. Other kinds help
avoid repeated questions and generate appropriate next steps. Conflicting facts must
be clarified; accepting AI wording does not create knowledge.

Exact questions and answers are saved together. Updates preserve the earlier file
in `history/`. Archive incorrect facts to exclude them from future runs. Previous
runs retain an evidence snapshot, so changing knowledge does not silently rewrite an
already reviewed resume. Regenerate a draft to incorporate corrected knowledge.

For the current personal collection, the AI reads the complete active KB before
asking questions. There is no embedding-only store and no potentially lossy top-k
filter. Embeddings can later be a rebuildable retrieval cache; JSON remains canonical.

Set `SCULPT_KNOWLEDGE_DIR` to a durable directory when hosting. The free Render
filesystem is temporary; local files on your own machine persist between runs.
Back up this folder yourself; local persistence does not protect against disk loss.

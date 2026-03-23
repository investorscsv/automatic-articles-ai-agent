# automatic-articles-ai-agent

A stateful CLI workflow for generating, reviewing, and publishing blog articles.

## What changed

The project now works as a resumable pipeline with explicit approval checkpoints:

1. Refresh the MongoDB snapshot of already published articles.
2. Generate a new topic and let you approve, edit, or regenerate it.
3. Build SEO metadata and let you approve or edit it.
4. Generate the article body once the topic and SEO are approved.
5. Generate a cover image, save it locally, and ask you to approve or regenerate it.
6. Ask whether the final article should be published.
7. Publish to Spaces and MongoDB only after explicit approval.

## How to run

```bash
python main.py
```

## Important files

- `generated_articles/workflow/state.json` — current workflow state for resumability.
- `generated_articles/source_data/existing_articles.json` — latest MongoDB snapshot.
- `generated_articles/topic_generation/latest_topic.json` — latest approved topic payload.
- `generated_articles/en/<slug>/` — article draft, metadata, and images.

## Notes

- All workflow prompts are in English.
- Topic and SEO fields can be edited directly in the console during approval.
- The article body is generated once approved and is not edited in the console.
- The image is saved to disk for local review because most terminals cannot display images inline.

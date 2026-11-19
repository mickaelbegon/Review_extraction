---
description: Extract all not-yet-processed PDFs of a folder with the review-extractor subagent (subscription, no API)
argument-hint: [pdf_folder=pdf_input] [out_folder=outputs_claude_agent]
---

Folder of PDFs: first argument (default `pdf_input`). Output folder: second argument (default `outputs_claude_agent`).

1. List the PDFs of the folder and skip those whose `<name>.json` already exists in the output folder (resume).
2. Launch the `review-extractor` subagent for the remaining PDFs, at most 3 at a time (subscription limits), passing
   the PDF path and the output folder. One subagent per PDF; never process two PDFs in one agent.
   Add to every subagent prompt: "Mandatory: after prepare, read the Figures section of form.md and open with the Read
   tool every `high` priority image it lists before answering the segment and joint items; open `low` ones if an item
   is still unresolved. Fill the author affiliation fields from the title page/footnotes. End your one-line reply with
   'figures opened: <pages or none>'."
3. When done, report: processed count, skipped count, failures, and the total number of answers flagged
   `review_required` (read `<out>/summary.csv`). If a usage limit is hit, stop and say that rerunning the command resumes.

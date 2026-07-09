# Update Log

## 2026-07-09

- Main issue: the old redaction path was not scalable for multilingual files. It forced English-first handling, could halt on pure Chinese documents when the English analyzer returned nothing, and made mixed-language processing depend on duplicated branch logic and exported workflow references.
- Main solution: split redaction into a reusable child workflow, route documents by language in the parent workflow, run mixed documents as sequential `zh` then `en` passes, and make empty analyzer/anonymizer outcomes continue safely instead of stopping the run.
- Documentation updates: refreshed the README setup/import steps, added the workflow-selection screenshot, and updated `Workflow_Logic.md` to match the new sub-workflow design and node behavior.
- Minor documentation cleanup: fixed the prior-arts list formatting so the Excel example displays correctly on GitHub.

## Notes

- This log records documentation and workflow-description updates made during the current maintenance pass.
- Future workflow or documentation changes can be appended here as new dated entries.

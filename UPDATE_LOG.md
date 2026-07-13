# Update Log

## 2026-07-13

- Main issue: the evaluation flow still used a penalty-and-threshold decision tree for the pre-commercialisation recommendation states, and the HTML assessment report was rendering the old hold logic instead of simply reflecting Node A's output.
- Main solution: simplified the pre-advance recommendation path to use penalised weighted-sum bands only, kept the advance-to-commercialisation gate criteria unchanged, and updated the assessment report node to render the precomputed decision matrix without recalculating any scores.
- Documentation updates: refreshed `Workflow_Logic.md` to describe the simplified decision matrix, clarified that the assessment report is a pure renderer, and removed the obsolete hold-threshold constants from the business-logic reference.

## 2026-07-09

- Main issue: the old redaction path was not scalable for multilingual files. It forced English-first handling, could halt on pure Chinese documents when the English analyzer returned nothing, and made mixed-language processing depend on duplicated branch logic and exported workflow references.
- Main solution: split redaction into a reusable child workflow, route documents by language in the parent workflow, run mixed documents as sequential `zh` then `en` passes, and make empty analyzer/anonymizer outcomes continue safely instead of stopping the run.
- Documentation updates: refreshed the README setup/import steps, added the workflow-selection screenshot, and updated `Workflow_Logic.md` to match the new sub-workflow design and node behavior.
- Minor documentation cleanup: fixed the prior-arts list formatting so the Excel example displays correctly on GitHub.

## Notes

- This log records documentation and workflow-description updates made during the current maintenance pass.
- Future workflow or documentation changes can be appended here as new dated entries.

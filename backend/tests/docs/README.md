# Local Evaluation Documents (Not Committed)

This directory is intentionally kept out of source control for legal/compliance
reasons. Public repositories should not redistribute third-party PDFs unless
you have explicit rights to do so.

## How to use

1. Place your local evaluation PDFs in this folder.
2. Update question JSON files in `backend/tests/eval/` to reference your local paths.
3. Run evals as usual (for example `python tests/eval/run_qa_eval.py ...`).

## Repository policy

- Allowed in git: this `README.md` and `.gitignore` only.
- Not allowed in git: any document payloads (PDF/DOCX/etc.) you do not own or
  cannot legally redistribute.

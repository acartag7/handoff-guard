---
name: update-docs
description: Update project documentation (README.md, AGENTS.md, example READMEs) to reflect current codebase state.
user-invocable: true
allowed-tools: Read, Glob, Grep, Edit, Bash
---

# Update Documentation

This skill updates the project's documentation files to reflect the current state of the codebase.

## Files Updated

1. **`README.md`** (project root) — Public-facing README with API docs and examples
2. **`AGENTS.md`** (project root) — Guide for AI coding agents
3. **`examples/llm_demo/README.md`** — LLM demo documentation
4. **`examples/rag_demo/README.md`** — RAG demo documentation

## Process

### Step 1: Scan for Changes

1. **Library source:**
   ```
   Glob: src/handoff/**/*.py
   ```
   Check for new/removed files, public API changes, new exports in `__init__.py`.

2. **Public API:**
   ```
   Read: src/handoff/__init__.py
   ```
   Verify `__all__` matches what's documented in README and AGENTS.md.

3. **Guard decorator:**
   ```
   Read: src/handoff/guard.py
   ```
   Check for new parameters, changed defaults, new on_fail modes.

4. **Retry system:**
   ```
   Read: src/handoff/retry.py
   ```
   Check for new RetryState properties, new Diagnostic fields, proxy changes.

5. **Utilities:**
   ```
   Read: src/handoff/utils.py
   ```
   Check for new utility functions or changed behavior.

6. **Examples:**
   ```
   Glob: examples/**/*.py
   ```
   Check for new demos, changed CLI flags, new agent patterns.

7. **Tests:**
   ```
   Glob: tests/test_*.py
   ```
   Check for new test files or significantly expanded coverage areas.

8. **Package config:**
   ```
   Read: pyproject.toml
   ```
   Check version, dependencies, optional extras.

### Step 2: Update README.md

- **Hero example**: Verify it uses current API correctly (`guard`, `retry`, `parse_json`)
- **Quick Start**: Verify install command and demo commands work
- **Features list**: Add any new features, remove deprecated ones
- **API section**: Sync `@guard` params, `retry` proxy properties, `parse_json` behavior, `HandoffViolation` attributes with actual source
- **Handle Failures**: Verify on_fail modes match implementation
- **Examples table**: Verify both demo links and descriptions are accurate
- **LangGraph section**: Verify `guarded_node` API is current
- **Comparison table**: Update if positioning has changed
- **Roadmap**: Check off completed items, add new planned items

### Step 3: Update AGENTS.md

- **Repository Structure**: Match current file tree exactly — no deleted files, no missing new files
- **Public API**: Sync imports with `__init__.py` `__all__`
- **@guard decorator**: Sync all parameters and their defaults with `guard.py`
- **retry proxy**: Sync all properties with `_RetryProxy` class in `retry.py`
- **HandoffViolation**: Sync attributes with `core.py`
- **Architecture Decisions**: Add any new decisions, remove outdated ones
- **Development Commands**: Verify all commands work, especially demo commands with current CLI flags
- **Testing section**: List all test files with accurate descriptions of what they cover

### Step 4: Update Example READMEs

For each example README (`examples/llm_demo/README.md`, `examples/rag_demo/README.md`):

- **Quick Start commands**: Verify all CLI flags match `argparse` in `run_demo.py`
- **Pipeline diagram**: Verify stages match actual agent/function names
- **Key Patterns code**: Verify code snippet matches actual implementation
- **Schemas table**: Verify schema names and validation rules match `schemas.py`
- **Requirements**: Verify install commands and dependencies

### Step 5: Report Summary

Output a summary of changes:
```
## Documentation Update Summary

### README.md
- Updated: API section (new guard parameter X)
- Updated: Features list (added Y)

### AGENTS.md
- Updated: Repository Structure (new file Z)
- Updated: Testing section (new test file)

### examples/llm_demo/README.md
- No changes needed

### examples/rag_demo/README.md
- Updated: Schemas table (new field in RAGOutput)
```

## Important Notes

- Keep README.md concise and user-facing — it's for people evaluating the library
- Keep AGENTS.md comprehensive — it's for AI agents working on the code
- Don't remove documentation for features that still exist
- Verify code examples in README actually work (correct imports, correct API)
- Keep the roadmap in README.md up to date — check off shipped features
- Example READMEs should match the actual CLI interface exactly

## When to Run

- After adding new public API (new exports, new guard parameters, new retry properties)
- After adding or removing source files
- After changing CLI flags in demo runners
- After adding new test files
- After changing package version or dependencies
- Before releasing a new version

---
description: Initialize project with CLAUDE.md and devcontainer setup
---

> Vendored from Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) (MIT). Upstream remains
> canonical. Local delta: the host-file block below.


Initialize this project for Claude Code and Grok Build.

## Host file

- If `AGENTS.md` exists, edit `AGENTS.md`. If `CLAUDE.md` is missing, `ln -s AGENTS.md CLAUDE.md`.
- Else create `AGENTS.md`, then `ln -s AGENTS.md CLAUDE.md`.
- If `CLAUDE.md` already exists and is a real file, edit `CLAUDE.md` and do not replace it with a symlink.

Devcontainer steps are the same on both hosts. "CLAUDE.md" in the tasks below means the host file.

## Tasks

1. **Create the host file if it doesn't exist:**
   - Analyze the project structure, build system, and testing setup (use `tree` command)
   - Document common commands (build, test, lint, dev server)
   - Note the architecture and key files
   - Add any project-specific conventions

2. **Create .devcontainer/devcontainer.json if it doesn't exist:**
   - First check if `.devcontainer/devcontainer.json` already exists - if so, skip this step
   - Create the `.devcontainer` directory if needed
   - Detect the project's primary language and use the appropriate Docker image:

   **Language Detection Rules (check in order):**
   - `Cargo.toml` exists → `"image": "rust:latest"`
   - `requirements.txt`, `pyproject.toml`, `setup.py`, or `Pipfile` exists → `"image": "python:latest"`
   - `go.mod` exists → `"image": "golang:latest"`
   - `Gemfile` exists → `"image": "ruby:latest"`
   - `pom.xml` or `build.gradle` exists → `"image": "eclipse-temurin:latest"`
   - `composer.json` exists → `"image": "php:latest"`
   - `*.csproj` or `*.fsproj` exists → `"image": "mcr.microsoft.com/dotnet/sdk:latest"`
   - `Package.swift` exists → `"image": "swift:latest"`
   - `package.json` exists → `"image": "node:lts"`
   - **Default** → `"image": "node:lts"`

   **devcontainer.json format:**
   ```json
   {
     "name": "dev",
     "image": "<detected-image>"
   }
   ```

3. **Report what was created:**
   - Summarize what files were created or already existed
   - Note the detected language and chosen Docker image for devcontainer

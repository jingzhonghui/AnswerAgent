#!/bin/bash
set -e

TARGET="/app/skills"
BUILTIN="/app/skills_builtin"

mkdir -p "$TARGET"

if [ -d "$BUILTIN" ]; then
    for skill_dir in "$BUILTIN"/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        if [ -d "$TARGET/$skill_name" ]; then
            echo "[entrypoint] Skill already exists, skipping: $skill_name"
        else
            cp -r "$skill_dir" "$TARGET/$skill_name"
            echo "[entrypoint] Copied built-in skill: $skill_name"
        fi
    done
fi

exec "$@"
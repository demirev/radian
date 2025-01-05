# Magenta

Magenta is a skeleton FastAPI project, containing basic scaffolding for an agentic LLM application.

The intended use is as a starting point for new FastAPI projects that utilize LLM agents. A typical workflow includes adding magenta as a git subtree and expand with new endpoints, moodels, services, etc based on business requirements. The core LLM calling, tool use, RAG etc is reused from magenta.

## Adding to existing project
Add to existing project using:

```
git remote add magenta-remote git@github.com:demirev/magenta.git
git subtree add --prefix magenta magenta-remote main --squash
```

## Pulling updates from magenta
Update using: 

```
git subtree pull --prefix magenta magenta-remote main --squash
```

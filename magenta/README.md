Add to existing project using:

```
git remote add magenta-remote git@github.com:demirev/magenta.git
git subtree add --prefix magenta magenta-remote main --squash
```

Update using: 

```
git subtree pull --prefix magenta magenta-remote main --squash
```

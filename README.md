Add to existing project using:

```
git remote add magenta-remote https://github.com/demirev/magenta.git
git subtree add --prefix app/magenta magenta-remote main --squash
```

Update using: 

```
git subtree pull --prefix app/magenta magenta-remote main --squash
```

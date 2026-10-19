# play-browser

[Play!](https://github.com/jpd002/Play-) (a PlayStation 2 emulator) built for the browser —
`Play.js` + `Play.wasm` — from a **pinned upstream commit**, and published as a GitHub
release so a web host can fetch it by URL and check it by sha256.

Upstream builds the same target in its own CI (`.github/workflows/build-js.yaml`) and
deploys it to playjs.purei.org, but publishes no versioned files. This repo exists so that
a host can serve a known build, roll back to the previous one, and bump deliberately.

## What's in a release

`play-browser-<version>.tar.gz` unpacks to one directory:

| file | |
|---|---|
| `Play.js` | the Emscripten module (ES6, `MODULARIZE`, pthreads — the page needs `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`) |
| `Play.wasm` | the emulator |
| `MANIFEST` | upstream commit, emsdk version, patches applied, build run |
| `SHA256SUMS` | of `Play.js` and `Play.wasm` |
| `LICENSE-Play.txt` | upstream's licence |

Next to it, `play-browser-<version>.tar.gz.sha256` holds the archive's digest (the same
number GitHub shows on the asset).

## Pins and patches

- `play-commit` — the upstream commit that gets built. Bump it, open a PR, and the PR
  build shows whether it still compiles and whether the patches still apply.
- `emsdk-version` — the Emscripten SDK version (upstream's CI pins the same one).
- `patches/*.patch` — applied with `git apply` before the build, in name order:
  - `0001-link-idbfs.patch`: links Emscripten's IDBFS so a page can mount an IndexedDB
    filesystem over Play!'s data directory (memory cards, config) and keep saves across
    reloads — upstream's build has only the in-memory filesystem. Also exports `HEAPU8`
    explicitly (a `discImageDevice` writes disc sectors into it; newer emsdks stop
    exporting the heap views by default).

## Releasing

A tag `v<version>` (or **Run workflow** with a version) builds and publishes the release;
every push and PR builds and uploads the same archive as a workflow artifact. Version
strings are `<upstream commit date>-<n>`, e.g. `2026.09.03-1`; the `-n` counts builds of the
same upstream commit (a new patch, a new emsdk).

## Using it

```js
import Play from "./Play.js";
const Module = await Play({
  locateFile: (p) => new URL(p, engineBaseUrl).href,   // where Play.wasm (and Play.js, for its workers) live
  mainScriptUrlOrBlob: new URL("Play.js", engineBaseUrl).href,
});
Module.FS.mkdir("/work");
Module.discImageDevice = { getFileSize() {…}, read(dstPtr, offset, size) {…}, isDone() {…} };
Module.ccall("initVm", "", [], []);           // needs <canvas id="outputCanvas" width="640" height="480">
Module.bootDiscImage("Game Name.iso");        // the extension picks the image format
```

Input is the keyboard, on the canvas (see `Source/ui_js/Main.cpp` upstream for the keys).
The disc is read through `Module.discImageDevice`, so it can come from a `File` (upstream's
page) or from anywhere else a page can read bytes from.

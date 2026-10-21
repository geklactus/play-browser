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
  - `0002-keyboard-digit-codes.patch`: the shoulder buttons and stick clicks are bound
    to `Key1`…`Key9`, which no keyboard sends — `KeyboardEvent.code` for the number row is
    `Digit1`…`Digit9`. Bound to the real codes, so L1/L2/L3 and R1/R2/R3 work from a
    keyboard (1 2 3 and 8 9 0).
  - `0003-openal-prebuffer.patch`: the sound handler queues one ~100 ms block at a time
    and restarts the OpenAL source the moment it runs dry, so it has no slack at all: any
    late block is an audible gap. In the browser the blocks are scheduled by the main
    thread, which is also proxying every WebGL call the GS makes, and it is late often.
    The source now waits for three queued blocks (~300 ms) before it (re)starts.
  - `0004-openal-rate-control.patch`: the emulator's clock and the audio device's never
    quite agree, and with the queue above never running dry the faster one wins — the
    queue grew a block at a time until `MAX_BUFFERS` (2.5 s of delay between the game
    and what you hear). The handler now holds the queue near its three blocks by nudging
    the source's pitch 0.2 % per half block of smoothed drift (1 % at most, inaudible),
    changing it only when the step changes; a queue ten blocks deep (the device paused)
    drops the block instead of adding to the delay.
  - `0005-present-whole-frames.patch`: the GS thread's WebGL calls are proxied to the
    main thread in batches and the browser composites the canvas between batches, so a
    frame could be shown half drawn, the rest of it then drawn onto a buffer the
    compositor had just cleared — flicker. The context is created with
    `explicitSwapControl`, so rendering goes to an offscreen framebuffer, and
    `PresentBackbuffer()` commits it to the canvas once per flip, whole.
  - `0006-field-present-offset.patch`: games that render in *field mode* (SMODE2
    interlaced with FFMD set — Onimusha 2, for one) draw each field into its own
    half-height buffer, the odd field with `XYOFFSET` moved half a line up (the SDK's
    `sceGsSetHalfOffset`), so that on a TV its lines fall between the even field's.
    Play! presents both buffers the same way, so the picture bobs by a line sixty times
    a second. The renderer now keeps, per buffer, the offset most of the primitives
    drawn into it since it was last shown used (most, not last: Onimusha 2 ends each
    field with one quad at a fixed offset) and, in field mode, samples the field that
    was drawn higher that much lower — the same "bob" deinterlacing other emulators
    default to. Which field is the higher one is read from the offsets themselves, not
    from the CSR field bit, so a game's own top-or-bottom-first convention doesn't
    matter; frame mode and progressive output are untouched. Measured on Onimusha 2's
    title and menu: 1.3–1.4 px of bob between fields before, under 0.2 px after.
  - `0007-framebuffer-redeclare-writeback.patch`: the renderer keeps one GL texture per
    *declaration* of a piece of GS memory (base pointer, width, format), and drawing
    updates the texture, never the memory. When a game declares the same memory again
    with another width — Onimusha 2 plays its movies in 640-wide field buffers over the
    512-wide ones its title and menus drew into — the new texture started from the
    memory as it was before any of that drawing, and the rows the movie never redraws
    (its letterbox bars) kept showing what had been uploaded there long before: pieces
    of the title screen, at the wrong stride. Each framebuffer now remembers how many
    rows have been drawn into it, and before a new framebuffer is created over memory
    an existing one drew into, those rows are read back and written to GS memory the
    way the hardware would hold them (pages a transfer wrote more recently are left
    alone), so the new framebuffer starts from them. Only 32-bit buffers are written
    back; a one-time read-back per new buffer geometry, nothing per frame.
- One tweak to the SDK itself, made by the workflow before the build (`Widen Emscripten's
  OpenAL scheduling window`): Emscripten's `library_openal.js` never schedules more than
  100 ms of queued audio ahead of the clock, which would make the pre-buffer pointless —
  a main-thread pause longer than 100 ms is a gap however much is queued. It is raised to
  500 ms. The step is pinned to the exact source text and fails if a new emsdk changes it;
  the package step checks the value reached `Play.js`.

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

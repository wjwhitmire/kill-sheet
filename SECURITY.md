# Security

## What the browser tool does with your data

- The page makes no network requests of any kind: no fetch, XHR, WebSocket, beacons or analytics. The only external resource is the Google Fonts stylesheet.
- No data leaves the browser. Well data you type or load from a file is processed in memory and is never uploaded or stored.
- Files are read with the browser's FileReader from a file you pick. Files over 5 MB or 50,000 rows are refused.
- localStorage holds one UI convenience only (oilfield or metric units). It never holds well data.
- The page uses no eval, no `new Function`, and no inline event handlers. User-supplied text is inserted with `textContent`, never `innerHTML`.
- The GitHub Pages build (`docs/index.html`) adds a Content-Security-Policy meta tag with `connect-src 'none'`.

## Python library

The library has no runtime dependencies, makes no network calls, and uses no pickle, eval or shell calls. The CLI reads only the file path you pass it.

## Safety

This is a training and cross-check aid. The rig's approved kill sheet and the well-site supervisor govern. If you find a calculation error, treat it as a security issue and report it as below.

## Reporting a problem

Open a GitHub issue with the label `security`, or use GitHub's private vulnerability reporting on this repository if the issue should not be public. Include the inputs, the steps to reproduce, and the browser or Python version.

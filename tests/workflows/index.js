// Lets `node --test tests/workflows/` run this folder: Node 22 resolves a directory argument
// as a module (this file) instead of searching it for test files.
import('./executor.test.mjs')

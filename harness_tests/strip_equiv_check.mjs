// Run by g_strip_equivalence. Imports the REAL ui/src/room/tags.js — not a regex
// rebuilt from its source text — and runs extractTags over the shared leak corpus,
// printing the resulting display texts as one JSON array on stdout.
//
// WHY AN IMPORT AND NOT A TEXT SCAN. tags_mirror_check.js reads the file as text and
// asserts its patterns MATCH; it was green for three weeks while `if (!kind) return _m`
// handed every matched mark straight back to his screen (SWEEP-2026-08-24 F2). The only
// assertion that means anything here is that the text a real caller gets back is CLEAN,
// and the only way to make it is to call the real function.
//
// tags.js is an ES module inside ui/ (no "type": "module" in scope here), so it is
// copied to a temp .mjs and imported by file URL — the import path node actually allows.
import { readFileSync, writeFileSync, mkdtempSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { pathToFileURL } from 'url'

const [, , tagsPath, corpusPath] = process.argv
if (!tagsPath || !corpusPath) {
  console.error('usage: node strip_equiv_check.mjs <tags.js> <strip_corpus.jsonl>')
  process.exit(2)
}
const dir = mkdtempSync(join(tmpdir(), 'stripq-'))
const mjs = join(dir, 'tags.mjs')
writeFileSync(mjs, readFileSync(tagsPath, 'utf8'))
const { extractTags } = await import(pathToFileURL(mjs).href)

const rows = readFileSync(corpusPath, 'utf8')
  .split('\n').filter(Boolean).map((l) => JSON.parse(l))
  .filter((r) => !r.why)
console.log(JSON.stringify(rows.map((r) => extractTags(r.input).text)))

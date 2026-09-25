/* fonts — self-hosted, so the room reads the same on every machine and works offline.
 * Inter for the UI, JetBrains Mono for what a machine says, Source Serif 4 for her words.
 * Each @font-face carries a unicode-range, so a browser fetches only the latin files;
 * the other subsets are emitted into the build and never requested. */
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import '@fontsource-variable/source-serif-4/wght.css'

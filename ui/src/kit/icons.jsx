/* icons — ONE drawn family (2026-09-24, his call: hand-drawn, in the repo, no library).
 *
 * 24-unit grid, 1.6 stroke, round caps and joins, currentColor. Each glyph may carry ONE
 * detail stroke, `ui-ic-d`, drawn in her live mood hue — so the whole desktop shifts
 * slightly when she does, and never enough to compete with the words.
 *
 * Names are the registry ids (appRegistry `icon:`), plus the shell's own marks.
 * G-ROOM-TOKENS leg 2 fails if a registry row names a glyph that is not here.
 */
export const GLYPHS = {
  chat: ['M4 5.5h16v10.5H9.5L4 20z', 'M8.5 10.5h7'],
  roomview: ['M5.5 5h13a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
             'M3.5 14.5c3-2 5-2 8.5 0s5.5 2 8.5 0'],
  apps: ['M4.5 4.5h6v6h-6zM13.5 4.5h6v6h-6zM4.5 13.5h6v6h-6z', 'M13.5 13.5h6v6h-6z'],
  settings: ['M4.5 7h9.5M18 7h1.5M4.5 17h1.5M10 17h9.5',
             'M14 7a2 2 0 1 0 4 0 2 2 0 1 0-4 0M6 17a2 2 0 1 0 4 0 2 2 0 1 0-4 0'],
  setup: ['M9.5 6.5h10M9.5 12h10M9.5 17.5h10',
          'M4.5 6.5l1 1 2-2M4.5 12l1 1 2-2M4.5 17.5l1 1 2-2'],
  voice: ['M12 4a3 3 0 0 1 3 3v4a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3zM6 11a6 6 0 0 0 12 0M12 17v3',
          'M9 20h6'],
  search: ['M10.5 4.5a6 6 0 1 0 0 12 6 6 0 1 0 0-12zM15 15l4.5 4.5', 'M8 9a3 3 0 0 1 2.5-2'],
  wardrobe: ['M12 7.5a1.8 1.8 0 1 1 1.8-1.8c0 1-1.8 1.4-1.8 2.8l8 5.5c.8.6.4 1.5-.5 1.5H4.5c-.9 0-1.3-.9-.5-1.5l8-5.5',
             'M7 18.5h10'],
  senses: ['M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z',
           'M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 1 0 0-5z'],
  tools: ['M15 4.5a4.5 4.5 0 0 0-4.2 6.1L4.5 16.9a1.8 1.8 0 0 0 2.6 2.6l6.3-6.3A4.5 4.5 0 0 0 19.5 9l-2.8 2.8-2.9-.6-.6-2.9L16 5.5a4.5 4.5 0 0 0-1-1z',
          'M6.5 17.5h.01'],
  board: ['M8 5H6.5A1.5 1.5 0 0 0 5 6.5v12A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-12A1.5 1.5 0 0 0 17.5 5H16M9 3.5h6v3H9z',
          'M8.5 11h7M8.5 15h4.5'],
  body: ['M12 20s-7-4.3-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.7-7 10-7 10z',
         'M8 12h2l1-2 2 4 1-2h2'],
  house: ['M4 11 12 4.5 20 11M6 9.5V19h12V9.5', 'M10.5 19v-4.5h3V19'],
  memory: ['M9.5 18.5a3 3 0 0 1-3-3 3 3 0 0 1-1.5-5.5A3 3 0 0 1 9 5a3 3 0 0 1 3 1.5V19M14.5 18.5a3 3 0 0 0 3-3 3 3 0 0 0 1.5-5.5A3 3 0 0 0 15 5a3 3 0 0 0-3 1.5',
           'M11 12a1 1 0 1 0 2 0 1 1 0 1 0-2 0'],
  decisions: ['M12 4v16M8 20h8M5 7h14M5 7l-2.5 6a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z',
              'M12 4h.01'],
  music: ['M9 17.5V6l10-2v11.5M9 17.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM19 15.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z',
          'M9 9.5l10-2'],
  agency: ['M12 4a8 8 0 1 0 0 16 8 8 0 1 0 0-16zM12 8v4l2.5 2',
           'M19 2.5l.5 1.5 1.5.5-1.5.5-.5 1.5-.5-1.5-1.5-.5 1.5-.5z'],
  research: ['M6 3.5h8l4 4V12M6 3.5A1.5 1.5 0 0 0 4.5 5v14A1.5 1.5 0 0 0 6 20.5h5M14 3.5v4h4',
             'M16.5 14a2.5 2.5 0 1 0 0 5 2.5 2.5 0 1 0 0-5zM18.3 18.8l1.7 1.7'],
  journal: ['M6 4.5h10.5a1.5 1.5 0 0 1 1.5 1.5v13.5H7.5A1.5 1.5 0 0 1 6 18zM6 18a1.5 1.5 0 0 1 1.5-1.5H18',
            'M9.5 8.5h5'],
  story: ['M12 6.5C10.5 5.3 8.3 4.5 4 4.5v13c4.3 0 6.5.8 8 2 1.5-1.2 3.7-2 8-2v-13c-4.3 0-6.5.8-8 2zM12 6.5v13',
          'M7 8.5h2.5M14.5 8.5H17'],
  files: ['M3.5 7A1.5 1.5 0 0 1 5 5.5h4l2 2h8A1.5 1.5 0 0 1 20.5 9v8.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z',
          'M3.5 10.5h17'],
  stage: ['M4 4.5h16M5 4.5v15M19 4.5v15M5 4.5c1 4 3 6 5 6.5M19 4.5c-1 4-3 6-5 6.5',
          'M9.5 19.5h5M12 14v5.5'],
  games: ['M12 4.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 1 0 0-5zM10 9.5l-1 5h6l-1-5M8.5 14.5h7l1 3h-9zM6.5 19.5h11',
          'M9.5 12h5'],
  ledger: ['M5 4.5h14v15H5zM5 9h14M5 14h14', 'M8 6.75h3M8 11.5h5M8 16.5h4'],
  room: ['M9 4.5h6l3 7H6zM12 11.5V19M8 19.5h8', 'M12 13.5h.01'],
  presence: ['M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z', 'M17 6h.01'],
  librarians: ['M5 4.5h3.5v15H5zM10 4.5h3.5v15H10zM15.3 5.3l3.4-.9 3.3 14.4-3.4.9z',
               'M5 8h3.5M10 8h3.5'],
  // the shell's own marks
  brand: ['M12 3l9 9-9 9-9-9z', 'M12 8.5l3.5 3.5-3.5 3.5-3.5-3.5z'],
  anon: ['M12 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 1 0 0-7zM5 19.5a7 7 0 0 1 14 0'],
  anonOn: ['M4 12a3 3 0 1 0 6 0v-1.5H4zM14 12a3 3 0 1 0 6 0v-1.5h-6zM10 11.5c1.3-.7 2.7-.7 4 0M2.5 10.5H4M20 10.5h1.5'],
  power: ['M12 3.5v8M7 6.5a7 7 0 1 0 10 0'],
  console: ['M4.5 5.5h15v13h-15zM8 10l2.5 2L8 14', 'M12.5 14.5H16'],
}

export function Icon({ name, size = 20, className = '' }) {
  const g = GLYPHS[name]
  if (!g) {
    // A missing glyph is a visible square, never nothing: an empty tile reads as a bug
    // in the room, a square reads as "this icon is missing", which is the truth.
    return <span className={'ui-ic ui-ic-missing ' + className}
                 style={{ width: size, height: size }} aria-hidden="true" />
  }
  return (
    <svg className={'ui-ic ' + className} width={size} height={size} viewBox="0 0 24 24"
         fill="none" stroke="currentColor" strokeWidth="1.6"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={g[0]} />
      {g[1] ? <path className="ui-ic-d" d={g[1]} /> : null}
    </svg>
  )
}

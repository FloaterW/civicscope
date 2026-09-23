"""Reviewed table adapters shared by annual resale and quarterly rental imports."""
from collections import defaultdict
import re
from .pilot_trreb import EXPECTED
from .trreb_history import ALIASES


def glyph_rows(page, start, step, count, top, *, overprinted=False):
    chars = [c for c in page.chars if 5 < c['size'] < 8 and top < c['top'] < 578]
    names = defaultdict(list)
    for c in chars:
        if c['x0'] < start:
            names[round(c['top'], 1)].append(c)
    rows = []
    seen = set()

    def last_run(glyphs):
        # PDF paints the later run over an earlier overlapping run. Preserve
        # stream order; sorting first would interleave both strings.
        run = []
        for c in glyphs:
            if run and c['x0'] < run[-1]['x0'] - .1:
                run = []
            run.append(c)
        return run

    for baseline, name_chars in sorted(names.items()):
        if overprinted:
            name_chars = last_run(name_chars)
        raw_name = ' '.join(''.join(c['text'] for c in sorted(name_chars, key=lambda c: c['x0'])).split())
        if not raw_name:
            continue
        name = ALIASES.get(raw_name, raw_name)
        if name not in EXPECTED:
            raise ValueError(f'Unknown source area {raw_name!r}')
        if overprinted and name in seen:
            continue  # displaced duplicate mark below the visible source row
        seen.add(name)
        numeric_baseline = baseline
        if overprinted:
            first_cell = [c for c in chars if start <= c['x0'] < start + step
                          and c['text'].isdigit() and abs(c['top']-baseline) < 1]
            if not first_cell:
                raise ValueError(f'Missing numeric row anchor: {name}')
            numeric_baseline = min(first_cell, key=lambda c: abs(c['top']-baseline))['top']
        cells = []
        for index in range(count):
            left, right = start + step * index, start + step * (index + 1)
            glyphs = [c for c in chars if left <= c['x0'] < right and abs(c['top'] - numeric_baseline) < .2]
            if overprinted:
                glyphs = last_run(glyphs)
            cells.append(''.join(c['text'] for c in sorted(glyphs, key=lambda c: c['x0'])).strip())
        rows.append((name, cells))
    if len({name for name, _ in rows}) != len(rows):
        raise ValueError('Duplicate areas')
    return rows


def legacy_rows(page, count):
    rows = []
    for line in (page.extract_text() or '').splitlines():
        line = ' '.join(line.split())
        if not rows and count == 10 and line == '1 2 2 3 2 3 2 3 2 3':
            continue  # Reviewed 2020-Q2 header superscript footnote markers.
        name = next((n for n in sorted(EXPECTED | set(ALIASES), key=len, reverse=True) if line.startswith(n + ' ')), None)
        if name:
            cells = line[len(name):].split()
            if len(cells) != count:
                raise ValueError(f'Wrong cell count: {name}')
            rows.append((ALIASES.get(name, name), cells))
        else:
            # Do not silently classify an unfamiliar municipal data row as a
            # heading/footer. Numeric tails identify even partially malformed rows.
            tail = 0
            for token in reversed(line.split()):
                if not re.fullmatch(r'(?:\$?[\d,.]+%?|[-*]+|N/A)', token):
                    break
                tail += 1
            if tail >= 3:
                raise ValueError(f'Unknown source row: {line}')
    if len({name for name, _ in rows}) != len(rows):
        raise ValueError('Duplicate source areas')
    return rows

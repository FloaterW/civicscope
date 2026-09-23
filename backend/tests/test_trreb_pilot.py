"""Synthetic fixtures only; no licensed report tables committed."""
from copy import deepcopy

import pytest

from etl.pilot_trreb import EXPECTED, FIELDS, GROUPS, extract_page, number, validate


def valid_rows():
    rows = {name: {'source_area': name, **dict.fromkeys(FIELDS, 1)} for name in EXPECTED}
    for parent, children in {**GROUPS, 'All TRREB Areas': list(GROUPS)}.items():
        for field in ('sales', 'dollar_volume', 'new_listings', 'active_listings'):
            rows[parent][field] = sum(rows[c][field] for c in children)
    return list(rows.values())


@pytest.mark.parametrize('raw,expected', [('0', 0), ('1,234', 1234),
                                         ('-', None), ('N/A', None), ('**', None)])
def test_integer_and_missing(raw, expected):
    assert number(raw, 'sales') == expected


@pytest.mark.parametrize('raw', ['12,34', 'NaN', 'inf', '-1', '1e5', '12abc', ''])
def test_bad_numeric_cells_fail(raw):
    with pytest.raises(ValueError):
        number(raw, 'sales')


def test_decimal_and_integer_contract():
    assert number('34.1%', 'snlr_trend_pct') == 34.1
    assert number('$1,234', 'average_price') == 1234
    with pytest.raises(ValueError):
        number('1.5', 'sales')


@pytest.mark.parametrize('value,field', [('$123', 'sales'), ('12%', 'median_price'), ('1%', 'months_inventory_trend')])
def test_wrong_units_fail(value, field):
    with pytest.raises(ValueError):
        number(value, field)


def test_all_totals_and_price_reconcile():
    validate(valid_rows())


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'unknown', 'total', 'price'])
def test_corrupt_candidates_fail(mutation):
    rows = valid_rows()
    if mutation == 'duplicate':
        rows.append(deepcopy(rows[0]))
    elif mutation == 'missing':
        rows.pop()
    elif mutation == 'unknown':
        rows[0]['source_area'] = 'Unknown'
    elif mutation == 'total':
        rows[0]['new_listings'] += 1
    else:
        rows[0]['average_price'] = 100
    with pytest.raises(ValueError):
        validate(rows)


def test_missing_is_not_reconstructed():
    rows = valid_rows()
    next(r for r in rows if r['source_area'] == 'Ajax')['sales'] = None
    validate(rows)
    assert next(r for r in rows if r['source_area'] == 'Ajax')['sales'] is None


def test_dollar_rounding_not_count_tolerance():
    rows = valid_rows()
    next(r for r in rows if r['source_area'] == 'City of Toronto')['dollar_volume'] += 1
    validate(rows)
    next(r for r in rows if r['source_area'] == 'City of Toronto')['sales'] += 1
    with pytest.raises(ValueError):
        validate(rows)


class Page:
    width, height = 792, 612

    def __init__(self):
        self.chars = []
        for i, row in enumerate(sorted(valid_rows(), key=lambda r: r['source_area'])):
            baseline = 100 + i * 11
            self.add(row['source_area'], 12, baseline)
            for col, field in enumerate(FIELDS):
                self.add(str(row[field]), 85 + col * 64, baseline)
            # Hidden PDF artifacts: nearby displaced numbers and oversized Abc.
            self.add('999', 85, baseline - 1.44)
            self.add('Abc', 470, baseline, size=33)

    def add(self, text, x, y, size=6.48):
        self.chars.extend({'text': c, 'x0': x + i, 'top': y, 'size': size}
                          for i, c in enumerate(text))

    def crop(self, box):
        self.header = box[1] == 0
        return self

    def extract_text(self):
        return ('SUMMARY OF EXISTING HOME TRANSACTIONS All Home Types, March 2026'
                if self.header else 'Sales Dollar Volume Average Price Median Price New Listings '
                'SNLR Trend Active Listings Mos Inv SP/LP LDOM PDOM')


def test_layout_excludes_hidden_overlapping_text():
    rows = extract_page(Page(), '2026-03')
    assert len(rows) == 41
    assert next(r for r in rows if r['source_area'] == 'Ajax')['sales'] == 1


def test_wrong_period_and_dimensions_fail():
    with pytest.raises(ValueError):
        extract_page(Page(), '2026-04')
    page = Page()
    page.width = 612
    with pytest.raises(ValueError):
        extract_page(page, '2026-03')

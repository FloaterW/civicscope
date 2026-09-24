"""Small shared schema checks at import and public-read boundaries."""
import math
import re
from urllib.parse import urlsplit

from app.services.trreb_preview import MUNICIPALITIES

GEOGRAPHY_NOTE = 'TRREB municipal reporting area; Census boundary equivalence is not certified. No tract allocation.'
VINTAGE_NOTE = 'Year-end tables include revisions. Monthly figures retain their explicitly selected archived report vintage.'
ATTRIBUTION = 'Source: Toronto Regional Real Estate Board (TRREB), Market Watch. All home types.'


def validate_observation(row, pins=None):
    required = {'geoid', 'source_area', 'period', 'period_type', 'property_type', 'median_price', 'sales',
                'property_days', 'listing_days', 'source_url', 'source_page', 'source_sha256', 'warnings',
                'geography_note', 'vintage_note', 'attribution'}
    if not isinstance(row, dict) or set(row) != required:
        raise ValueError('Invalid observation shape')
    geoid = row['geoid']
    if not isinstance(geoid, str) or geoid not in MUNICIPALITIES or row['source_area'] != MUNICIPALITIES[geoid][0]:
        raise ValueError('Invalid reporting area')
    period = row['period']
    family = {'year': 'resale_annual', 'month': 'resale'}.get(row['period_type']) if isinstance(row['period_type'], str) else None
    pattern = r'202[0-5]' if family == 'resale_annual' else r'202[0-5]-(0[1-9]|1[0-2])'
    if not family or not isinstance(period, str) or not re.fullmatch(pattern, period):
        raise ValueError('Invalid observation period')
    if row['property_type'] != 'All home types':
        raise ValueError('Invalid property type')
    for field in ('median_price', 'sales', 'property_days', 'listing_days'):
        if type(row[field]) is not int or row[field] < 0:
            raise ValueError('Invalid resale headline statistic')
    if type(row['source_page']) is not int or row['source_page'] < 1:
        raise ValueError('Invalid source page')
    if not isinstance(row['source_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['source_sha256']):
        raise ValueError('Invalid source fingerprint')
    if pins is not None and pins.get((family, period)) != row['source_sha256']:
        raise ValueError('Observation does not match selected source vintage')
    if not isinstance(row['source_url'], str):
        raise ValueError('Invalid source URL')
    url = urlsplit(row['source_url'])
    if url.scheme != 'https' or url.hostname not in {'trreb.ca', 'www.trreb.ca', 'public.trreb.ca'} or url.username or url.password or url.port not in {None, 443}:
        raise ValueError('Invalid source URL')
    if row['geography_note'] != GEOGRAPHY_NOTE or row['vintage_note'] != VINTAGE_NOTE or row['attribution'] != ATTRIBUTION:
        raise ValueError('Invalid attribution or geography/vintage disclosure')
    if not isinstance(row['warnings'], list):
        raise ValueError('Invalid source warnings')
    for warning in row['warnings']:
        if not isinstance(warning, dict) or set(warning) != {'area', 'field', 'reported', 'children_sum', 'difference'}:
            raise ValueError('Invalid source warning')
        if not isinstance(warning['area'], str) or not isinstance(warning['field'], str) or warning['area'] not in MUNICIPALITIES[geoid] or warning['field'] not in {'sales', 'dollar_volume', 'new_listings', 'active_listings'}:
            raise ValueError('Invalid source warning context')
        for field in ('reported', 'children_sum', 'difference'):
            value = warning[field]
            if type(value) not in {int, float} or abs(value) > 10**18 or not math.isfinite(value):
                raise ValueError('Invalid source warning value')

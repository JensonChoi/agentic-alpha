"""Render the three daily-return charts from the experiment IDs in the benchmark tables.

From backend, run PYTHONPATH=. uv run python ../scripts/benchmark_charts.py.
"""
import re
from datetime import date
from math import ceil, floor
from pathlib import Path
from xml.etree import ElementTree as ET

from app.db import Experiment, Session

DOCS = Path(__file__).resolve().parents[1] / 'docs'
STYLES = [
    ('#414b5b', '7 4'), ('#845128', '3 4'), ('#126e64', ''), ('#9d3560', '8 3 2 3'),
    ('#3454b4', ''), ('#7842a0', ''), ('#3454b4', '8 4'), ('#7842a0', '8 4'), ('#b44c13', ''),
    ('#b44c13', '8 4'),
]


def chart(year, series, low, high):
    start = date(year, 1, 1)
    end = max(points[-1][0] for _, points in series)

    def x(day):
        return 74 + 776 * (day - start).days / (end - start).days

    def y(value):
        return 319 - 259 * (value - low) / (high - low)

    height = 450 + 26 * max(0, (len(series) - 1) // 3 - 2)
    svg = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', viewBox=f'0 0 880 {height}', role='img',
                     attrib={'aria-labelledby': 'title desc'})
    ET.SubElement(svg, 'title', id='title').text = f'{year} cumulative portfolio returns'
    ET.SubElement(svg, 'desc', id='desc').text = 'Daily portfolio returns from $100,000 for the strategies in the results table.'
    ET.SubElement(svg, 'rect', width='880', height=str(height), rx='12', fill='white')
    group = ET.SubElement(svg, 'g', {'font-family': 'system-ui, sans-serif', 'fill': '#17243b'})

    def label(xpos, ypos, value, size=13, anchor='start'):
        ET.SubElement(group, 'text', {'x': f'{xpos:.2f}', 'y': f'{ypos:.2f}', 'font-size': str(size),
                                      'text-anchor': anchor}).text = value

    label(74, 35, f'{year} cumulative return', 23)
    for pct in range(low, high + 1, 20):
        ypos = y(pct)
        ET.SubElement(group, 'path', d=f'M74 {ypos:.2f} H850', stroke='#8593a5' if pct == 0 else '#e2e7ef')
        label(62, ypos + 4, f'{pct}%', anchor='end')
    for month in range(1, end.month + 1, 2):
        day = date(year, month, 1)
        ET.SubElement(group, 'path', d=f'M{x(day):.2f} 60 V319', stroke='#edf0f5')
        label(x(day), 340, day.strftime('%b'), anchor='middle')
    for index, (name, points) in enumerate(series):
        color, dash = STYLES[index]
        style = {'stroke': color, 'stroke-width': '2', 'fill': 'none'}
        if dash:
            style['stroke-dasharray'] = dash
        coords = ' '.join(f'{x(day):.2f},{y(value):.2f}' for day, value in points)
        ET.SubElement(group, 'polyline', style, points=coords)
        left = 74 + 260 * (index % 3)
        top = 364 + 26 * (index // 3)
        ET.SubElement(group, 'path', style, d=f'M{left} {top} h27')
        label(left + 35, top + 4, name)
    ET.indent(svg)
    return ET.tostring(svg, encoding='unicode') + '\n'


def render_report(report):
    years = {}
    with Session() as db:
        for year in (2026, 2025, 2024):
            section = report.split(f'### {year}\n', 1)[1].split('\n![', 1)[0]
            rows = re.findall(r'^\| ([^|]+?) \|.*?`([a-f0-9-]{36})` \|$', section, re.M)
            series = []
            for label, experiment_id in rows:
                experiment = db.get(Experiment, experiment_id)
                initial = experiment.config['initial_capital']
                points = [(date(year, 1, 1), 0.0)]
                points.extend((date.fromisoformat(p['date']), 100 * (p['equity']/initial - 1))
                              for p in experiment.result['equity'])
                series.append((label, points))
            if not 6 <= len(series) <= len(STYLES):
                raise ValueError(f'Unexpected table for {year}')
            years[year] = series
    values = [value for series in years.values() for _, points in series for _, value in points]
    low = min(-40, 20 * floor(min(values) / 20))
    high = max(80, 20 * ceil(max(values) / 20))
    return {year: chart(year, series, low, high) for year, series in years.items()}


def main():
    for year, svg in render_report((DOCS / 'benchmark-report.md').read_text()).items():
        (DOCS / 'images' / f'benchmark-returns-{year}.svg').write_text(svg)


if __name__ == '__main__':
    main()

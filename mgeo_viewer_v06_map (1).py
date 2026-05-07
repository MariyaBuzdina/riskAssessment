from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


INPUT_FILE = "mgeo_results_v05.xlsx"
OUTPUT_FILE = "mgeo_view_v06_map.html"

LABELS = {
    "f1": "f1 (глубина)",
    "f2": "f2 (лёд)",
    "f3": "f3 (стеснённость)",
    "f4": "f4 (гидрография)",
    "F": "F (итоговая оценка)",
}

DESCRIPTIONS = {
    "f1": "глубина относительно осадки судна",
    "f2": "толщина льда относительно ледопроходимости судна",
    "f3": "стеснённость относительно безопасной полосы маневрирования",
    "f4": "гидрографическая изученность",
    "F": "интегральная оценка: f1 × f2 × f3",
}


def project_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else project_dir() / path


def clean_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for record in df.to_dict("records"):
        row = {}
        for key, value in record.items():
            if pd.isna(value):
                row[key] = None
            elif hasattr(value, "item"):
                row[key] = value.item()
            else:
                row[key] = value
        records.append(row)
    return records


def read_results(path: Path) -> tuple[list[dict], list[dict]]:
    return (
        clean_records(pd.read_excel(path, sheet_name="route_results")),
        clean_records(pd.read_excel(path, sheet_name="segment_results")),
    )


def html_template(route_results: list[dict], segment_results: list[dict]) -> str:
    route_json = json.dumps(route_results, ensure_ascii=False)
    segment_json = json.dumps(segment_results, ensure_ascii=False)
    labels_json = json.dumps(LABELS, ensure_ascii=False)
    descriptions_json = json.dumps(DESCRIPTIONS, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Оценка навигационного риска</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #111; background: #fff; }}
.page {{ max-width: 1440px; margin: 0 auto; padding: 16px 22px 24px 22px; }}
.title {{ font-size: 16px; margin-bottom: 10px; }}
.controls {{ display: grid; grid-template-columns: 1.1fr 1.1fr 1fr 1fr 0.9fr 1fr; gap: 8px; margin-bottom: 10px; align-items: end; }}
label {{ display: block; font-size: 12px; margin-bottom: 3px; }}
select {{ width: 100%; box-sizing: border-box; padding: 6px; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: 1.35fr 0.9fr; gap: 12px; align-items: start; }}
.panel {{ border: 1px solid #d0d0d0; padding: 10px; background: #fff; }}
#map {{ width: 100%; height: 690px; border: 1px solid #d0d0d0; background: #eef2f4; }}
.legend {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; }}
.gradient {{ height: 12px; flex: 1; background: linear-gradient(to right, #cc0000, #ff8c00, #ffd400, #9acd32, #008000); border: 1px solid #bbb; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border: 1px solid #d0d0d0; padding: 5px 6px; text-align: left; vertical-align: top; }}
th {{ background: #f2f2f2; position: sticky; top: 0; z-index: 1; }}
.tablebox {{ max-height: 690px; overflow: auto; }}
.note {{ margin-top: 8px; font-size: 12px; color: #444; }}
.route-title {{ margin: 0 0 8px 0; font-size: 14px; }}
.leaflet-tooltip.route-tooltip {{ font-size: 12px; padding: 3px 5px; }}
.legend-box {{ margin-bottom: 10px; border: 1px solid #d0d0d0; background: #fafafa; padding: 8px; font-size: 12px; }}
.legend-row {{ display: grid; grid-template-columns: 145px 1fr; gap: 8px; margin-bottom: 4px; }}
@media (max-width: 1050px) {{ .controls {{ grid-template-columns: 1fr 1fr; }} .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="page">
  <div class="title">Оценка навигационного риска</div>
  <div class="controls">
    <div><label>Акватория</label><select id="waterArea"></select></div>
    <div><label>Маршрут</label><select id="route"></select></div>
    <div><label>Судно</label><select id="vessel"></select></div>
    <div><label>Месяц</label><select id="season"></select></div>
    <div><label>Критерий карты</label><select id="criterion"><option value="F">F (итог)</option><option value="f1">f1</option><option value="f2">f2</option><option value="f3">f3</option><option value="f4">f4</option></select></div>
    <div><label>Раскраска</label><select id="colorMode"><option value="route">маршрут целиком</option><option value="segment">по отрезкам</option></select></div>
  </div>
  <div class="grid">
    <div class="panel">
      <div id="map"></div>
      <div class="legend"><span>0</span><div class="gradient"></div><span>1</span></div>
      <div class="note">Показывается только выбранный маршрут. Карта загружается через OpenStreetMap. F = f1 × f2 × f3.</div>
    </div>
    <div class="panel tablebox">
      <div class="legend-box" id="legendBox"></div>
      <p class="route-title" id="routeTitle"></p>
      <table id="summaryTable"></table>
      <br>
      <table id="segmentTable"></table>
    </div>
  </div>
</div>
<script>
const ROUTE_RESULTS = {route_json};
const SEGMENT_RESULTS = {segment_json};
const LABELS = {labels_json};
const DESCRIPTIONS = {descriptions_json};
let map = null;
let layerGroup = null;
let tileLayer = null;

const controls = {{
  waterArea: document.getElementById("waterArea"),
  route: document.getElementById("route"),
  vessel: document.getElementById("vessel"),
  season: document.getElementById("season"),
  criterion: document.getElementById("criterion"),
  colorMode: document.getElementById("colorMode")
}};

function uniqueSorted(rows, key) {{
  return [...new Set(rows.map(r => r[key]).filter(v => v !== null && v !== undefined))]
    .sort((a,b)=>String(a).localeCompare(String(b), "ru"));
}}

function routeDisplay(value) {{
  const text = String(value || "");
  const match = text.match(/route_?(\\d+)/i);
  if (match) return "маршрут " + match[1].padStart(2, "0");
  return text.replace(/route/ig, "маршрут");
}}

function fillSelect(select, values, displayFn = null) {{
  const old = select.value;
  select.innerHTML = "";
  for (const value of values) {{
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = displayFn ? displayFn(value) : value;
    select.appendChild(opt);
  }}
  if (values.includes(old)) select.value = old;
}}

function initControls() {{
  fillSelect(controls.waterArea, uniqueSorted(ROUTE_RESULTS, "water_area_name"));
  updateRouteSelect();
  fillSelect(controls.vessel, uniqueSorted(ROUTE_RESULTS, "vessel_name"));
  controls.vessel.value = ROUTE_RESULTS.some(r => r.vessel_name === "Кристоф де Маржери") ? "Кристоф де Маржери" : controls.vessel.options[0].value;
  const seasons = [...new Map(ROUTE_RESULTS.map(r => [r.season, r.season_name])).entries()];
  controls.season.innerHTML = "";
  for (const [code, name] of seasons) {{
    const opt = document.createElement("option"); opt.value = code; opt.textContent = name; controls.season.appendChild(opt);
  }}
  controls.waterArea.addEventListener("change", () => {{ updateRouteSelect(); render(); }});
  for (const key of ["route", "vessel", "season", "criterion", "colorMode"]) controls[key].addEventListener("change", render);
}}

function updateRouteSelect() {{
  const rows = ROUTE_RESULTS.filter(r => r.water_area_name === controls.waterArea.value);
  fillSelect(controls.route, uniqueSorted(rows, "route_name"), routeDisplay);
}}

function valueColor(value) {{
  const v = Math.max(0, Math.min(1, Number(value)));
  const stops = [[0,[204,0,0]],[0.25,[255,140,0]],[0.5,[255,212,0]],[0.75,[154,205,50]],[1,[0,128,0]]];
  for (let i = 0; i < stops.length - 1; i++) {{
    const [ap,a] = stops[i], [bp,b] = stops[i+1];
    if (v >= ap && v <= bp) {{
      const t = (v - ap) / (bp - ap);
      const rgb = a.map((x,j)=>Math.round(x + (b[j] - x) * t));
      return `rgb(${{rgb[0]}},${{rgb[1]}},${{rgb[2]}})`;
    }}
  }}
  return "rgb(0,128,0)";
}}

function selectedRouteResult() {{
  return ROUTE_RESULTS.find(r =>
    r.water_area_name === controls.waterArea.value &&
    r.route_name === controls.route.value &&
    r.vessel_name === controls.vessel.value &&
    r.season === controls.season.value
  );
}}

function selectedSegments() {{
  const route = selectedRouteResult();
  if (!route) return [];
  return SEGMENT_RESULTS.filter(s =>
    s.route_id === route.route_id &&
    s.vessel_name === controls.vessel.value &&
    s.season === controls.season.value
  ).sort((a,b)=>Number(a.segment_no)-Number(b.segment_no));
}}

function ensureMap() {{
  if (map) return;
  map = L.map("map", {{ zoomControl: true }});
  map.attributionControl.setPrefix(false);
  tileLayer = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    maxZoom: 18,
    attribution: "© OpenStreetMap"
  }}).addTo(map);
  layerGroup = L.layerGroup().addTo(map);
}}

function renderMap(route, segments) {{
  ensureMap();
  layerGroup.clearLayers();
  if (!route || !segments.length) return;
  const criterion = controls.criterion.value;
  const bounds = [];
  const routeValue = Number(route[criterion]);
  for (const s of segments) {{
    const value = controls.colorMode.value === "route" ? routeValue : Number(s[criterion]);
    const latlngs = [[Number(s.lat_start), Number(s.lon_start)], [Number(s.lat_end), Number(s.lon_end)]];
    bounds.push(latlngs[0], latlngs[1]);
    const line = L.polyline(latlngs, {{ color: valueColor(value), weight: 6, opacity: 0.92 }});
    line.bindTooltip(`${{route.water_area_name}} / ${{routeDisplay(route.route_name)}}<br>${{LABELS[criterion]}} = ${{value.toFixed(4)}}<br>отрезок ${{s.segment_no}}`, {{sticky: true, className: "route-tooltip"}});
    line.addTo(layerGroup);
  }}
  const first = segments[0];
  const last = segments[segments.length - 1];
  L.circleMarker([Number(first.lat_start), Number(first.lon_start)], {{radius: 5, color: "#111", fillColor: "#fff", fillOpacity: 1, weight: 2}}).bindTooltip("Начало").addTo(layerGroup);
  L.circleMarker([Number(last.lat_end), Number(last.lon_end)], {{radius: 5, color: "#111", fillColor: "#111", fillOpacity: 1, weight: 2}}).bindTooltip("Конец").addTo(layerGroup);
  map.fitBounds(bounds, {{ padding: [24, 24] }});
}}

function renderLegend() {{
  const box = document.getElementById("legendBox");
  box.innerHTML = "";
  for (const key of ["f1", "f2", "f3", "f4", "F"]) {{
    const row = document.createElement("div");
    row.className = "legend-row";
    const left = document.createElement("div");
    const right = document.createElement("div");
    left.textContent = LABELS[key];
    right.textContent = DESCRIPTIONS[key];
    row.appendChild(left);
    row.appendChild(right);
    box.appendChild(row);
  }}
}}

function limitingDisplay(value) {{
  if (value === "f1") return "f1 (глубина)";
  if (value === "f2") return "f2 (лёд)";
  if (value === "f3") return "f3 (стеснённость)";
  return value;
}}

function renderSummaryTable(route) {{
  const title = document.getElementById("routeTitle");
  const table = document.getElementById("summaryTable");
  const criterion = controls.criterion.value;
  table.innerHTML = "";
  if (!route) {{ title.textContent = "Маршрут не найден"; return; }}
  title.textContent = `${{route.water_area_name}} / ${{routeDisplay(route.route_name)}} / ${{route.vessel_name}} / ${{route.season_name}}`;
  const heads = ["f1", "f2", "f3", "f4", "F", "Ограничивает"];
  const values = [route.f1, route.f2, route.f3, route.f4, route.F, limitingDisplay(route.limiting_factor)];
  const trh = document.createElement("tr");
  for (const h of heads) {{
    const th = document.createElement("th");
    th.textContent = LABELS[h] || h;
    if (h === criterion) th.style.outline = "2px solid #111";
    trh.appendChild(th);
  }}
  table.appendChild(trh);
  const tr = document.createElement("tr");
  values.forEach((v, idx) => {{
    const td = document.createElement("td");
    td.textContent = typeof v === "number" && idx <= 4 ? v.toFixed(4) : v;
    if (idx <= 4) td.style.background = valueColor(v);
    if (["f1", "f2", "f3", "f4", "F"][idx] === criterion) td.style.outline = "2px solid #111";
    tr.appendChild(td);
  }});
  table.appendChild(tr);
}}

function renderSegmentTable(segments) {{
  const table = document.getElementById("segmentTable");
  const criterion = controls.criterion.value;
  table.innerHTML = "";
  const heads = ["Отрезок", "f1", "f2", "f3", "f4", "F"];
  const trh = document.createElement("tr");
  for (const h of heads) {{
    const th = document.createElement("th");
    th.textContent = LABELS[h] || h;
    if (h === criterion) th.style.outline = "2px solid #111";
    trh.appendChild(th);
  }}
  table.appendChild(trh);
  for (const s of segments) {{
    const tr = document.createElement("tr");
    const vals = [s.segment_no, s.f1, s.f2, s.f3, s.f4, s.F];
    vals.forEach((v, idx) => {{
      const td = document.createElement("td");
      td.textContent = typeof v === "number" && idx >= 1 ? v.toFixed(4) : v;
      if (idx >= 1) td.style.background = valueColor(v);
      if (["f1", "f2", "f3", "f4", "F"][idx-1] === criterion) td.style.outline = "2px solid #111";
      tr.appendChild(td);
    }});
    table.appendChild(tr);
  }}
}}

function render() {{
  const route = selectedRouteResult();
  const segments = selectedSegments();
  renderLegend();
  renderMap(route, segments);
  renderSummaryTable(route);
  renderSegmentTable(segments);
}}

initControls();
setTimeout(render, 100);
</script>
</body>
</html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mGeo: карта одного выбранного маршрута без F4")
    parser.add_argument("--input", default=INPUT_FILE)
    parser.add_argument("--output", default=OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    route_results, segment_results = read_results(input_path)
    output_path.write_text(html_template(route_results, segment_results), encoding="utf-8")
    print("Готово")
    print(f"Входной файл: {input_path.name}")
    print(f"Выходной файл: {output_path.name}")


if __name__ == "__main__":
    main()

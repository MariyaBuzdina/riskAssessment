from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


INPUT_FILE = "mgeo_normalized_input_v01_ext.xlsx"
OUTPUT_FILE = "mgeo_results_v05.xlsx"

SEASONS: Dict[str, Dict[str, str]] = {
    "apr": {"name": "апрель", "ice_col": "ice_apr", "vessel_ice_col": "ice_capability_ws", "period": "зима/весна"},
    "may": {"name": "май", "ice_col": "ice_may", "vessel_ice_col": "ice_capability_ws", "period": "зима/весна"},
    "jun": {"name": "июнь", "ice_col": "ice_jun", "vessel_ice_col": "ice_capability_ws", "period": "зима/весна"},
    "aug": {"name": "август", "ice_col": "ice_aug", "vessel_ice_col": "ice_capability_ls", "period": "лето/осень"},
    "oct": {"name": "октябрь", "ice_col": "ice_oct", "vessel_ice_col": "ice_capability_ls", "period": "лето/осень"},
    "dec": {"name": "декабрь", "ice_col": "ice_dec", "vessel_ice_col": "ice_capability_ws", "period": "зима/весна"},
}

POINT_CRITERIA = ["f1", "f2", "f3", "f4", "F"]
LIMITING_FIELDS = ["f1", "f2", "f3"]


def project_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else project_dir() / path


def to_number(value: Any) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        text = value.strip().lower().replace(",", ".")
        if text in {"inf", "+inf", "infinity", "+infinity"}:
            return math.inf
        if text in {"", "nan", "none", "null"}:
            return np.nan
        return float(text)
    return float(value)


def clamp(value: float) -> float:
    if pd.isna(value):
        return np.nan
    return max(0.0, min(1.0, float(value)))


def read_normalized(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    routes = pd.read_excel(path, sheet_name="routes", dtype=object).dropna(how="all")
    points = pd.read_excel(path, sheet_name="route_points", dtype=object).dropna(how="all")
    vessels = pd.read_excel(path, sheet_name="vessels", dtype=object).dropna(how="all")

    numeric_points = [
        "point_no", "lat", "lon", "ice_apr", "ice_may", "ice_jun", "ice_aug", "ice_oct", "ice_dec",
        "depth", "constriction_fact", "hydro_fact", "hydro_proj",
    ]
    numeric_vessels = ["draft", "safe_lane_width", "ice_capability_ls", "ice_capability_ws"]

    for col in numeric_points:
        points[col] = points[col].map(to_number)
    for col in numeric_vessels:
        vessels[col] = vessels[col].map(to_number)

    validate_input(routes, points, vessels)
    return routes, points, vessels


def validate_input(routes: pd.DataFrame, points: pd.DataFrame, vessels: pd.DataFrame) -> None:
    if routes["route_id"].duplicated().any():
        raise ValueError("Дубли route_id")
    if vessels["vessel_id"].duplicated().any():
        raise ValueError("Дубли vessel_id")
    if set(points["route_id"]) - set(routes["route_id"]):
        raise ValueError("В route_points есть route_id, которых нет в routes")
    if points.duplicated(["route_id", "point_no"]).any():
        raise ValueError("Дубли route_id + point_no")


def f1_depth(draft: float, depth: float) -> float:
    if pd.isna(depth) or depth <= 0:
        return 0.0
    return clamp(1.0 - draft / depth)


def f2_ice(ice: float, vessel_ice: float) -> float:
    if math.isinf(vessel_ice):
        return 1.0
    if pd.isna(vessel_ice) or vessel_ice <= 0:
        return 0.0
    return clamp(1.0 - ice / (1.25 * vessel_ice))


def f3_constriction(safe_lane_width: float, constriction_fact: float) -> float:
    if math.isinf(constriction_fact):
        return 1.0
    if pd.isna(constriction_fact) or constriction_fact <= 0:
        return 0.0
    return clamp(1.0 - safe_lane_width / constriction_fact)


def f4_hydro(hydro_proj: float, hydro_fact: float) -> float:
    if pd.isna(hydro_proj):
        return 1.0
    if math.isinf(hydro_fact):
        return 0.0
    if pd.isna(hydro_fact) or hydro_fact <= 0:
        return 0.0
    return clamp(hydro_proj / hydro_fact)


def limiting_factor(row: pd.Series) -> str:
    values = {field: float(row[field]) for field in LIMITING_FIELDS}
    return min(values, key=values.get)


def calculate_point_results(routes: pd.DataFrame, points: pd.DataFrame, vessels: pd.DataFrame) -> pd.DataFrame:
    parts = []

    for _, vessel in vessels.iterrows():
        for season_code, season in SEASONS.items():
            df = points.copy()
            df["vessel_id"] = vessel["vessel_id"]
            df["vessel_name"] = vessel["vessel_name"]
            df["season"] = season_code
            df["season_name"] = season["name"]
            df["season_period"] = season["period"]
            df["draft"] = vessel["draft"]
            df["safe_lane_width"] = vessel["safe_lane_width"]
            df["selected_ice"] = df[season["ice_col"]]
            df["selected_ice_capability"] = vessel[season["vessel_ice_col"]]
            df["f1"] = [f1_depth(vessel["draft"], depth) for depth in df["depth"]]
            df["f2"] = [f2_ice(ice, vessel[season["vessel_ice_col"]]) for ice in df["selected_ice"]]
            df["f3"] = [f3_constriction(vessel["safe_lane_width"], width) for width in df["constriction_fact"]]
            df["f4"] = [f4_hydro(proj, fact) for proj, fact in zip(df["hydro_proj"], df["hydro_fact"])]
            df["F"] = [clamp(a * b * c) for a, b, c in zip(df["f1"], df["f2"], df["f3"])]
            df["limiting_factor"] = df.apply(limiting_factor, axis=1)
            parts.append(df)

    result = pd.concat(parts, ignore_index=True).merge(routes, on="route_id", how="left")
    cols = [
        "water_area_id", "water_area_name", "route_id", "route_name", "point_no", "lat", "lon",
        "vessel_id", "vessel_name", "season", "season_name", "season_period", "draft", "safe_lane_width",
        "selected_ice", "selected_ice_capability", "depth", "constriction_fact", "hydro_fact", "hydro_proj",
        "f1", "f2", "f3", "f4", "F", "limiting_factor", "source_file", "source_sheet",
    ]
    return result[cols].sort_values(["vessel_id", "season", "route_id", "point_no"]).reset_index(drop=True)


def calculate_segment_results(point_results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sort_cols = ["vessel_id", "season", "route_id", "point_no"]

    for _, df in point_results.sort_values(sort_cols).groupby(["vessel_id", "season", "route_id"], sort=False):
        df = df.reset_index(drop=True)
        for i in range(len(df) - 1):
            a = df.iloc[i]
            b = df.iloc[i + 1]
            row = {
                "water_area_id": a["water_area_id"],
                "water_area_name": a["water_area_name"],
                "route_id": a["route_id"],
                "route_name": a["route_name"],
                "segment_no": i + 1,
                "point_start": int(a["point_no"]),
                "point_end": int(b["point_no"]),
                "lat_start": a["lat"],
                "lon_start": a["lon"],
                "lat_end": b["lat"],
                "lon_end": b["lon"],
                "vessel_id": a["vessel_id"],
                "vessel_name": a["vessel_name"],
                "season": a["season"],
                "season_name": a["season_name"],
                "season_period": a["season_period"],
                "source_file": a["source_file"],
                "source_sheet": a["source_sheet"],
            }
            for criterion in POINT_CRITERIA:
                row[criterion] = min(float(a[criterion]), float(b[criterion]))
            row["limiting_factor"] = limiting_factor(pd.Series(row))
            rows.append(row)

    return pd.DataFrame(rows).sort_values(["vessel_id", "season", "route_id", "segment_no"]).reset_index(drop=True)


def calculate_route_results(segment_results: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "water_area_id", "water_area_name", "route_id", "route_name", "vessel_id", "vessel_name",
        "season", "season_name", "season_period", "source_file", "source_sheet",
    ]
    result = segment_results.groupby(group_cols, as_index=False)[POINT_CRITERIA].min()
    counts = segment_results.groupby(group_cols, as_index=False)["segment_no"].count().rename(columns={"segment_no": "segments_count"})
    result = result.merge(counts, on=group_cols, how="left")
    result["limiting_factor"] = result.apply(limiting_factor, axis=1)
    cols = [
        "water_area_id", "water_area_name", "route_id", "route_name", "segments_count", "vessel_id", "vessel_name",
        "season", "season_name", "season_period", "f1", "f2", "f3", "f4", "F", "limiting_factor",
        "source_file", "source_sheet",
    ]
    return result[cols].sort_values(["vessel_id", "season", "water_area_id", "route_id"]).reset_index(drop=True)


def export_results(
    path: Path,
    routes: pd.DataFrame,
    points: pd.DataFrame,
    vessels: pd.DataFrame,
    point_results: pd.DataFrame,
    segment_results: pd.DataFrame,
    route_results: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        routes.to_excel(writer, sheet_name="routes", index=False)
        points.to_excel(writer, sheet_name="route_points", index=False)
        vessels.to_excel(writer, sheet_name="vessels", index=False)
        route_results.to_excel(writer, sheet_name="route_results", index=False)
        segment_results.to_excel(writer, sheet_name="segment_results", index=False)
        point_results.to_excel(writer, sheet_name="point_results", index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mGeo: расчет по модели без F4")
    parser.add_argument("--input", default=INPUT_FILE)
    parser.add_argument("--output", default=OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    routes, points, vessels = read_normalized(input_path)
    point_results = calculate_point_results(routes, points, vessels)
    segment_results = calculate_segment_results(point_results)
    route_results = calculate_route_results(segment_results)
    export_results(output_path, routes, points, vessels, point_results, segment_results, route_results)

    print("Готово")
    print(f"Входной файл: {input_path.name}")
    print(f"Выходной файл: {output_path.name}")
    print(f"Маршрутов: {len(routes)}")
    print(f"Точек маршрутов: {len(points)}")
    print(f"Судов: {len(vessels)}")
    print(f"Сезонов: {len(SEASONS)}")
    print(f"Строк по маршрутам: {len(route_results)}")


if __name__ == "__main__":
    main()

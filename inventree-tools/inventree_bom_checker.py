#!/usr/bin/env python3
"""Compare an external BOM file with current InvenTree stock."""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

DEFAULT_CONFIG = {
    "server": os.environ.get("INVENTREE_SERVER", "http://127.0.0.1:8000"),
    "token": os.environ.get("INVENTREE_TOKEN", ""),
    "username": os.environ.get("INVENTREE_USERNAME", ""),
    "password": os.environ.get("INVENTREE_PASSWORD", ""),
    "input": "",
    "output": str(SCRIPT_DIR / "reports"),
    "watch": "",
    "watch_interval_seconds": 30,
    "match_fields": ["ipn", "name", "description"],
    "stock_field": "unallocated_stock",
    "search_fallback": False,
    "field_mapping": {},
}

FIELD_ALIASES = {
    "ref": ["元件编号", "编号", "位号", "reference", "ref", "refdes", "reference designator", "reference_designator"],
    "mpn": ["型号", "规格", "厂家型号", "制造商型号", "mpn", "part number", "part_number", "part name", "part_name", "value"],
    "package": ["封装", "package", "footprint", "packaging"],
    "qty": ["数量", "qty", "quantity", "count"],
    "designators": ["位号", "designator", "refdes", "reference designator", "reference_designator"],
    "description": ["描述", "description", "comment", "商品名称"],
    "lcsc": ["lcsc", "lcsc编号", "lcsc code", "商品编号"],
}


def log_message(message, config=None):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    if config and config.get("log_file"):
        Path(config["log_file"]).parent.mkdir(parents=True, exist_ok=True)
        with open(config["log_file"], "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def load_config(path):
    config = dict(DEFAULT_CONFIG)
    if path and Path(path).is_file():
        with open(path, "r", encoding="utf-8") as handle:
            config.update(json.load(handle))
    return config


def request_json(url, headers=None, timeout=30):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"InvenTree API 返回 {exc.code}: {detail[:500]}") from exc


def get_api_token(server, username, password):
    if not username or not password:
        raise RuntimeError("使用用户名登录时需要同时提供 INVENTREE_USERNAME 和 INVENTREE_PASSWORD。")
    raw = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(raw).decode("ascii")
    data = request_json(
        server.rstrip("/") + "/api/user/me/token/",
        headers={"Authorization": f"Basic {auth}"},
    )
    token = data.get("token") if isinstance(data, dict) else None
    if not token:
        raise RuntimeError("未能从 InvenTree 获取 API Token。")
    return token


def api_get_all(server, token, path, params=None):
    if not token:
        raise RuntimeError("缺少 InvenTree API Token。")
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    url = server.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    results = []
    while url:
        payload = request_json(url, headers=headers)
        if isinstance(payload, list):
            results.extend(payload)
            break
        if isinstance(payload, dict) and "results" in payload:
            results.extend(payload["results"])
            url = payload.get("next")
        else:
            results.append(payload)
            break
    return results


def normalize_key(value):
    return re.sub(r"[\s_\-/]+", "", str(value or "")).upper()


def parse_number(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    if "/" in text and re.fullmatch(r"\d+\s*/\s*\d+", text):
        top, bottom = re.split(r"\s*/\s*", text)
        return float(top) / float(bottom)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else 0.0


def normalize_header(value):
    return re.sub(r"[\s_\-]+", "", str(value or "")).lower()


def detect_columns(header_row):
    normalized = [normalize_header(value) for value in header_row]
    columns = {}
    for field, aliases in FIELD_ALIASES.items():
        normalized_aliases = [normalize_header(alias) for alias in aliases]
        exact = next(
            (idx for idx, value in enumerate(normalized) if value in normalized_aliases),
            None,
        )
        if exact is not None:
            columns[field] = exact
            continue
        for idx, value in enumerate(normalized):
            if any(alias and alias in value for alias in normalized_aliases):
                columns[field] = idx
                break
    return columns


def apply_custom_mapping(columns, header_row, custom_mapping):
    if not custom_mapping:
        return columns
    normalized = [normalize_header(value) for value in header_row]
    for field, header_name in custom_mapping.items():
        key = normalize_header(header_name)
        if key in normalized:
            columns[field] = normalized.index(key)
    return columns


def parse_xlsx(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared_strings = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.iter(f"{XLSX_NS}si"):
                shared_strings.append("".join(t.text or "" for t in si.iter(f"{XLSX_NS}t")))

        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in names:
            candidates = [name for name in names if re.match(r"xl/worksheets/sheet\d+\.xml$", name)]
            if not candidates:
                raise ValueError("Excel 文件中没有找到工作表。")
            sheet_name = sorted(candidates)[0]

        root = ET.fromstring(archive.read(sheet_name))
        rows = []
        for row_el in root.iter(f"{XLSX_NS}row"):
            cells = {}
            for cell in row_el.findall(f"{XLSX_NS}c"):
                ref = cell.get("r", "")
                match = re.match(r"([A-Z]+)", ref or "")
                if not match:
                    continue
                col = 0
                for char in match.group(1):
                    col = col * 26 + (ord(char.upper()) - 64)
                col -= 1
                cell_type = cell.get("t", "")
                value_el = cell.find(f"{XLSX_NS}v")
                value = ""
                if cell_type == "s" and value_el is not None:
                    pos = int(float(value_el.text or 0))
                    value = shared_strings[pos] if pos < len(shared_strings) else ""
                elif cell_type == "inlineStr":
                    inline = cell.find(f"{XLSX_NS}is")
                    if inline is not None:
                        value = "".join(t.text or "" for t in inline.iter(f"{XLSX_NS}t"))
                elif value_el is not None:
                    value = value_el.text or ""
                cells[col] = value
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(idx, "") for idx in range(width)])
        return rows


def parse_bom_file(path):
    suffix = Path(path).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return parse_xlsx(path)
    if suffix == ".xls":
        try:
            import xlrd
        except ImportError:
            raise ValueError("旧版 .xls 文件需要安装 xlrd，请改用 .xlsx 或 CSV。")
        book = xlrd.open_workbook(path)
        sheet = book.sheet_by_index(0)
        return [
            [str(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
            for row_idx in range(sheet.nrows)
        ]
    if suffix in (".csv", ".tsv", ".txt"):
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        delimiter = "\t" if suffix == ".tsv" else None
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ","
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    raise ValueError(f"不支持的文件类型：{suffix}")


def extract_bom_items(rows, custom_mapping=None):
    header_idx = None
    header_columns = None
    for idx, row in enumerate(rows):
        columns = detect_columns(row)
        if "mpn" in columns or "qty" in columns or "ref" in columns:
            header_idx = idx
            header_columns = apply_custom_mapping(columns, row, custom_mapping)
            break
    if header_idx is None:
        raise ValueError("没有识别到 BOM 表头，请检查列名是否包含 型号、数量、封装、位号 等字段。")

    items = {}
    for row in rows[header_idx + 1 :]:
        if not any(str(value or "").strip() for value in row):
            continue

        def cell(field):
            idx = header_columns.get(field)
            return str(row[idx]).strip() if idx is not None and idx < len(row) else ""

        ref = cell("ref")
        designators = cell("designators") or ref
        mpn = cell("mpn") or cell("lcsc")
        package = cell("package")
        description = cell("description")
        qty = parse_number(cell("qty"))
        if qty <= 0:
            qty = 1.0
        if not mpn and not ref:
            continue

        key = (normalize_key(mpn), normalize_key(package))
        if key not in items:
            items[key] = {
                "ref": ref,
                "mpn": mpn,
                "package": package,
                "description": description,
                "qty": 0.0,
                "designators": [],
            }
        item = items[key]
        item["qty"] += qty
        for token in re.split(r"[,;\s]+", designators):
            if token and token not in item["designators"]:
                item["designators"].append(token)
        if not item["mpn"] and mpn:
            item["mpn"] = mpn
        if not item["package"] and package:
            item["package"] = package
        if not item["description"] and description:
            item["description"] = description

    result = list(items.values())
    for item in result:
        item["designators"] = ", ".join(item["designators"])
    return result


def build_part_indexes(parts, match_fields):
    indexes = {}
    for field in match_fields:
        indexes[field] = {}
    for part in parts:
        for field in match_fields:
            value = part_value(part, field)
            key = normalize_key(value)
            if key and key not in indexes[field]:
                indexes[field][key] = part
    return indexes


def part_value(part, field):
    if field.startswith("metadata."):
        metadata = part.get("metadata") or {}
        return metadata.get(field[len("metadata.") :], "")
    return part.get(field, "")


def match_part(item, indexes, match_fields):
    key = normalize_key(item["mpn"])
    if not key:
        return None, None
    for field in match_fields:
        part = indexes.get(field, {}).get(key)
        if part:
            return part, field
    return None, None


def search_part_fallback(server, token, item, parts):
    term = (item.get("mpn") or "").strip()
    if not term:
        return None
    candidates = api_get_all(server, token, "/api/part/", {"search": term, "limit": 10})
    target = normalize_key(term)
    for part in candidates:
        for field in ("ipn", "name", "description"):
            if normalize_key(part.get(field, "")) == target:
                return part
        if target and target in normalize_key(part.get("name", "")):
            return part
    return None


def stock_quantity(part, config, server=None, token=None):
    preferred = config.get("stock_field", "unallocated_stock")
    for field in [preferred, "unallocated_stock", "available", "in_stock", "total_in_stock"]:
        if field in part and part[field] is not None:
            return float(part[field] or 0)
    if server and token:
        part_id = part.get("pk") or part.get("id")
        if part_id:
            items = api_get_all(
                server,
                token,
                "/api/stock/",
                {"part": part_id, "in_stock": "true", "limit": 1000, "page_size": 1000},
            )
            return sum(parse_number(item.get("quantity", 0)) for item in items)
    return 0.0


def generate_report(server, token, bom_items, config, dry_run=False):
    parts = [] if dry_run else api_get_all(
        server,
        token,
        "/api/part/",
        {"limit": 1000, "page_size": 1000, "ordering": "ipn"},
    )
    match_fields = config.get("match_fields") or ["ipn", "name"]
    indexes = build_part_indexes(parts, match_fields)

    report = []
    for item in bom_items:
        part, matched_field = match_part(item, indexes, match_fields)
        if not part and not dry_run and config.get("search_fallback"):
            part = search_part_fallback(server, token, item, parts)
            matched_field = "search"
        if part:
            stock = stock_quantity(part, config, server, token)
            shortage = max(0.0, item["qty"] - stock)
            status = "充足" if shortage <= 0 else "缺料"
            report.append(
                {
                    **item,
                    "status": status,
                    "stock": stock,
                    "shortage": shortage,
                    "part_id": part.get("pk") or part.get("id"),
                    "part_ipn": part.get("ipn", ""),
                    "part_name": part.get("name", ""),
                    "matched_field": matched_field,
                }
            )
        else:
            report.append(
                {
                    **item,
                    "status": "未匹配",
                    "stock": 0.0,
                    "shortage": item["qty"],
                    "part_id": "",
                    "part_ipn": "",
                    "part_name": "",
                    "matched_field": "",
                }
            )
    report.sort(key=lambda row: (row["status"] != "充足", -row["shortage"]))
    return report, len(parts)


def write_csv(report, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "位号",
                "型号/规格",
                "封装",
                "需求数量",
                "库存可用",
                "缺口",
                "状态",
                "InvenTree元件ID",
                "InvenTree IPN",
                "InvenTree名称",
                "匹配字段",
            ]
        )
        for row in report:
            writer.writerow(
                [
                    row["designators"],
                    row["mpn"],
                    row["package"],
                    f"{row['qty']:g}",
                    f"{row['stock']:g}",
                    f"{row['shortage']:g}",
                    row["status"],
                    row["part_id"],
                    row["part_ipn"],
                    row["part_name"],
                    row["matched_field"],
                ]
            )


def write_html(report, path, csv_name, bom_name):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    missing = sum(1 for row in report if row["status"] == "缺料")
    unmatched = sum(1 for row in report if row["status"] == "未匹配")
    rows_html = "".join(
        f"""
        <tr class="{ 'danger' if row['status'] == '缺料' else 'warn' if row['status'] == '未匹配' else 'ok' }">
          <td>{row['designators']}</td>
          <td>{row['mpn']}</td>
          <td>{row['package']}</td>
          <td class="num">{row['qty']:g}</td>
          <td class="num">{row['stock']:g}</td>
          <td class="num">{row['shortage']:g}</td>
          <td><span class="tag">{row['status']}</span></td>
          <td>{row['part_ipn']}</td>
          <td>{row['part_name']}</td>
        </tr>"""
        for row in report
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BOM 缺料对比 - {bom_name}</title>
<style>
body {{ margin: 0; padding: 24px; background: #f4f6f6; color: #172121; font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }}
.wrap {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 22px; margin: 0 0 6px; }}
.sub {{ color: #5f6e6e; margin-bottom: 18px; }}
.stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }}
.stat {{ background: #fff; border: 1px solid #dbe4e4; border-radius: 8px; padding: 12px 16px; }}
.stat b {{ display: block; font-size: 22px; }}
.toolbar {{ display: flex; gap: 10px; margin-bottom: 14px; }}
.btn {{ display: inline-flex; align-items: center; gap: 6px; background: #0f766e; color: #fff; border: 0; border-radius: 8px; padding: 10px 14px; text-decoration: none; font-weight: 600; }}
.table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #dbe4e4; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; min-width: 900px; }}
th, td {{ text-align: left; padding: 11px 12px; border-bottom: 1px solid #dbe4e4; }}
th {{ background: #eef3f3; font-size: 13px; }}
td.num {{ font-variant-numeric: tabular-nums; }}
tr.ok {{ background: #f7faf9; }}
tr.warn {{ background: #fdf3e2; }}
tr.danger {{ background: #fdeae7; }}
.tag {{ display: inline-flex; min-height: 22px; padding: 0 8px; border-radius: 999px; font-size: 12px; font-weight: 600; align-items: center; }}
.ok .tag {{ background: #d9f0ed; color: #0a4f4a; }}
.warn .tag {{ background: #fdeed3; color: #b45309; }}
.danger .tag {{ background: #fbe4e1; color: #b42318; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>BOM 缺料对比</h1>
  <div class="sub">源文件：{bom_name} · 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  <div class="stats">
    <div class="stat"><span>元件行数</span><b>{len(report)}</b></div>
    <div class="stat"><span>缺料</span><b>{missing}</b></div>
    <div class="stat"><span>未匹配</span><b>{unmatched}</b></div>
  </div>
  <div class="toolbar"><a class="btn" href="{csv_name}">导出 CSV</a></div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>位号</th><th>型号/规格</th><th>封装</th><th>需求数量</th><th>库存可用</th><th>缺口</th><th>状态</th><th>IPN</th><th>InvenTree 名称</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""
    Path(path).write_text(html, encoding="utf-8")


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_file(path, config, dry_run=False):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    rows = parse_bom_file(path)
    bom_items = extract_bom_items(rows, config.get("field_mapping"))
    if not bom_items:
        raise ValueError("BOM 中没有可处理的数据行。")

    report, part_count = generate_report(
        config.get("server", ""),
        config.get("token", ""),
        bom_items,
        config,
        dry_run=dry_run,
    )
    output_dir = Path(config.get("output") or SCRIPT_DIR / "reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"{path.stem}_{timestamp}_shortage.csv"
    html_path = output_dir / f"{path.stem}_{timestamp}_shortage.html"
    write_csv(report, csv_path)
    write_html(report, html_path, csv_path.name, path.name)

    missing = sum(1 for row in report if row["status"] == "缺料")
    unmatched = sum(1 for row in report if row["status"] == "未匹配")
    log_message(
        f"{path.name}: {len(report)} 行，缺料 {missing}，未匹配 {unmatched}；"
        f"已生成 {html_path.name} 和 {csv_path.name}"
        + (f"（dry-run，未连接 InvenTree，InvenTree 元件数 0）" if dry_run else ""),
        config,
    )
    return {"html": html_path, "csv": csv_path, "report": report}


def watch_loop(config, dry_run=False):
    watch_dir = Path(config.get("watch") or "")
    if not watch_dir.is_dir():
        raise FileNotFoundError(f"监控目录不存在：{watch_dir}")
    output_dir = Path(config.get("output") or SCRIPT_DIR / "reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "watched_files.json"
    state = {"files": {}}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {"files": {}}

    suffixes = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls")
    interval = max(1, int(config.get("watch_interval_seconds") or 30))
    log_message(f"开始监控目录：{watch_dir}（每 {interval} 秒检查一次）", config)
    while True:
        changed = False
        for path in sorted(watch_dir.iterdir()):
            if path.suffix.lower() not in suffixes or not path.is_file():
                continue
            digest = file_digest(path)
            if state["files"].get(str(path)) == digest:
                continue
            try:
                process_file(path, config, dry_run=dry_run)
                state["files"][str(path)] = digest
                changed = True
            except Exception as exc:
                log_message(f"{path.name} 处理失败：{exc}", config)
        if changed:
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(interval)


def main():
    default_config = os.environ.get("INVENTREE_BOM_CHECKER_CONFIG") or str(SCRIPT_DIR / "inventree_bom_checker.json")
    parser = argparse.ArgumentParser(description="外部 BOM 与 InvenTree 库存对比工具")
    parser.add_argument("--config", default=default_config, help="配置文件路径")
    parser.add_argument("--server", help="InvenTree 地址，例如 http://127.0.0.1:8000")
    parser.add_argument("--token", help="InvenTree API Token")
    parser.add_argument("--username", help="InvenTree 用户名")
    parser.add_argument("--password", help="InvenTree 密码")
    parser.add_argument("--input", help="要处理的 BOM 文件")
    parser.add_argument("--watch", help="监控目录")
    parser.add_argument("--output", help="报告输出目录")
    parser.add_argument("--interval", type=int, help="监控检查间隔（秒）")
    parser.add_argument("--match-fields", help="匹配字段，逗号分隔，例如 ipn,name,description")
    parser.add_argument("--stock-field", help="库存字段，例如 unallocated_stock 或 available")
    parser.add_argument("--log-file", help="日志文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只解析 BOM 并生成报告，不连接 InvenTree")
    args = parser.parse_args()

    config = load_config(args.config)
    for key, value in (
        ("server", args.server),
        ("token", args.token),
        ("username", args.username),
        ("password", args.password),
        ("input", args.input),
        ("watch", args.watch),
        ("output", args.output),
        ("log_file", args.log_file),
    ):
        if value is not None:
            config[key] = value
    if args.interval is not None:
        config["watch_interval_seconds"] = args.interval
    if args.match_fields:
        config["match_fields"] = [field.strip() for field in args.match_fields.split(",") if field.strip()]
    if args.stock_field:
        config["stock_field"] = args.stock_field

    try:
        if args.dry_run:
            if args.input:
                process_file(args.input, config, dry_run=True)
            elif args.watch:
                watch_loop(config, dry_run=True)
            else:
                parser.error("dry-run 需要 --input 或 --watch。")
            return

        token = config.get("token") or ""
        if not token and (config.get("username") or config.get("password")):
            token = get_api_token(config.get("server", ""), config.get("username", ""), config.get("password", ""))
            config["token"] = token
        if not token and not config.get("watch"):
            log_message("未配置 API Token；如使用用户名/密码，请填写 username 和 password。", config)

        if config.get("input"):
            process_file(config["input"], config)
        elif config.get("watch"):
            watch_loop(config)
        else:
            parser.error("请提供 --input 文件或 --watch 监控目录。")
    except Exception as exc:
        log_message(f"执行失败：{exc}", config)
        sys.exit(1)


if __name__ == "__main__":
    main()

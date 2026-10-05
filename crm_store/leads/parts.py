import json
from pathlib import Path

PART_LINE_LIMIT = 150


def json_line_count(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").count("\n")


def lead_chunks(leads, limit=PART_LINE_LIMIT):
    chunks = []
    current = []
    for lead in leads:
        if current and json_line_count(current + [lead]) > limit:
            chunks.append(current)
            current = [lead]
        else:
            current.append(lead)
    if current or not chunks:
        chunks.append(current)
    return chunks


def read_lead_parts(directory):
    leads = []
    for path in sorted(Path(directory).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            leads.extend(data)
        elif isinstance(data, dict):
            leads.append(data)
    return leads


def write_lead_parts(directory, leads, limit=PART_LINE_LIMIT):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    chunks = lead_chunks(leads, limit)
    written = set()
    for index, chunk in enumerate(chunks, start=1):
        name = f"part-{index:02d}.json"
        path = directory / name
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
        written.add(name)
    for path in directory.glob("*.json"):
        if path.name not in written:
            path.unlink()

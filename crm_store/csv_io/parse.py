import uuid
from datetime import timezone
from crm_store.statuses import BUSINESS_HEADER_WORDS, JUNK_HEADER, PHONE_HEADER_WORDS, REVIEW_HEADER_WORDS, TIMEZONE_HEADER_WORDS, utc_now
from crm_store.csv_io.fields import _phone
from crm_store.csv_io.fields import _read_csv
from crm_store.csv_io.fields import _review_count
from crm_store.csv_io.fields import _timezone
from crm_store.csv_io.fields import _unique_headers

def parse_csv(data, known_phones=()):
    rows = _read_csv(data)
    if not rows:
        return [], {"duplicates": 0, "skipped": 0, "columns": []}

    width = max(map(len, rows))
    rows = [row + [""] * (width - len(row)) for row in rows]
    first_has_phone = any(_phone(value) for value in rows[0])
    header = None if first_has_phone else _unique_headers(rows[0])
    records = rows[1:] if header else rows
    headers = header or [f"Column {index + 1}" for index in range(width)]
    hits = [sum(bool(_phone(row[column])) for row in records) for column in range(width)]

    phone_columns = []
    if header:
        phone_columns = [index for index, value in enumerate(header)
                         if any(word in value.lower() for word in PHONE_HEADER_WORDS)
                         and "fax" not in value.lower() and hits[index]]
    if not phone_columns and max(hits, default=0):
        phone_columns = [hits.index(max(hits))]

    used = set(phone_columns)
    first_name = next((i for i, value in enumerate(header or [])
                       if "first" in value.lower() and i not in used), None)
    last_name = next((i for i, value in enumerate(header or [])
                      if "last" in value.lower() and "name" in value.lower() and i not in used), None)
    full_name = next((i for i, value in enumerate(header or [])
                      if ("name" in value.lower() or "contact" in value.lower()) and i not in used
                      and i not in (first_name, last_name)), None)
    name_column = full_name
    business_column = next((i for i, value in enumerate(header or [])
                            if i not in used and any(word in value.lower() for word in BUSINESS_HEADER_WORDS)), None)
    if first_name is not None and last_name is not None:
        used.update((first_name, last_name))
    elif name_column is not None:
        used.add(name_column)
    if business_column is not None:
        used.add(business_column)
    timezone_column = next((i for i, value in enumerate(header or [])
                            if i not in used and any(word in value.lower() for word in TIMEZONE_HEADER_WORDS)), None)
    if timezone_column is not None:
        used.add(timezone_column)
    review_column = next((i for i, value in enumerate(header or [])
                          if i not in used and any(word in value.lower() for word in REVIEW_HEADER_WORDS)), None)
    if review_column is not None:
        used.add(review_column)

    text_columns = [i for i in range(width) if i not in used and hits[i] <= len(records) // 2
                    and not (header and JUNK_HEADER.search(header[i]))]
    if name_column is None and first_name is None and text_columns:
        name_column = text_columns.pop(0)
    if business_column is None and text_columns:
        business_column = text_columns.pop(0)

    seen = set(known_phones)
    leads = []
    duplicates = skipped = 0
    for row in records:
        phone = next((_phone(row[index]) for index in phone_columns if _phone(row[index])), None)
        if not phone:
            phone = next((_phone(value) for value in row if _phone(value)), None)
        if not phone:
            skipped += 1
            continue
        if phone in seen:
            duplicates += 1
            continue
        seen.add(phone)
        if first_name is not None and last_name is not None:
            name = f"{row[first_name]} {row[last_name]}".strip()
        else:
            name = row[name_column].strip() if name_column is not None else ""
        fields = {headers[index]: value for index, value in enumerate(row) if value}
        timezone = _timezone(row[timezone_column]) if timezone_column is not None else None
        review_count = _review_count(row[review_column]) if review_column is not None else None
        leads.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "business": row[business_column].strip() if business_column is not None else "",
            "phone": phone,
            "timezone": timezone or "Unknown",
            "review_count": review_count,
            "status": "new",
            "scheduled_until": None,
            "transcript": [],
            "fields": fields,
            "created_at": utc_now().isoformat(),
        })
    return leads, {"duplicates": duplicates, "skipped": skipped, "columns": headers}

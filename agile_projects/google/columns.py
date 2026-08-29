"""The sheet contract: which column holds what, and which are writable.

Kept free of any frappe import so it can be unit-tested with no bench.
"""

# (field, header, writable)
COLUMNS = [
    ("name", "Task ID", False),
    ("subject", "Subject", True),
    ("status", "Status", True),
    ("priority", "Priority", True),
    ("complexity_points", "Points", True),
    ("sme_responsible", "SME (Employee ID)", True),
    ("sme_name", "SME Name", False),
    ("exp_start_date", "Start", True),
    ("exp_end_date", "Due", True),
    ("progress", "Progress %", True),
    ("expected_time", "Estimated Hours", True),
    ("blocked_reason", "Blocked Reason", True),
    ("actual_time", "Logged Hours", False),
    # description is HTML in ERPNext; a spreadsheet round-trip would flatten
    # formatting on every sync, so it is pushed for reference only
    ("description", "Description (read-only)", False),
    ("modified", "Last Changed", False),
]

WIDTH = len(COLUMNS)
KEY_INDEX = 0
HEADERS = [header for _, header, _ in COLUMNS]
FIELDS = [field for field, _, _ in COLUMNS]
WRITABLE_FIELDS = [field for field, _, writable in COLUMNS if writable]
WRITABLE_INDEXES = {
    field: index for index, (field, _, writable) in enumerate(COLUMNS) if writable
}
# fields the sheet shows but the sync must never write back to ERPNext
READONLY_FIELDS = [field for field, _, writable in COLUMNS if not writable]


def column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


LAST_COLUMN = column_letter(WIDTH - 1)


def data_range(tab, first_row=1, last_row=None):
    """A1 range for the sheet's data block, bounded to our columns."""
    tab = tab.replace("'", "''")
    end = last_row if last_row else ""
    return f"'{tab}'!A{first_row}:{LAST_COLUMN}{end}"


def pad_rows(rows, width=WIDTH):
    """Google omits trailing empty cells, so rows come back ragged.

    Without this, reading column N of a row whose tail was blank raises
    IndexError.
    """
    padded = []
    for row in rows:
        row = list(row) if row else []
        if len(row) < width:
            row = row + [""] * (width - len(row))
        padded.append(row[:width])
    return padded


def build_row_index(rows, first_data_row=2):
    """Map Task ID -> sheet row number, and classify the odd rows.

    Row indexes are never cached between runs: users insert, delete and sort
    rows freely and protection cannot reliably stop them, so identity always
    comes from the key column.

    Returns (index, duplicates, new_rows, blank_rows).
    """
    index = {}
    duplicates = {}
    new_rows = []
    blank_rows = []

    for offset, row in enumerate(rows):
        row_number = first_data_row + offset
        key = str(row[KEY_INDEX]).strip() if len(row) > KEY_INDEX else ""
        has_content = any(str(cell).strip() for cell in row[KEY_INDEX + 1 :])

        if not key:
            if has_content:
                # someone typed a task straight into the sheet
                new_rows.append(row_number)
            else:
                blank_rows.append(row_number)
            continue

        if key in index:
            # a copy-pasted row; first occurrence wins deterministically
            duplicates.setdefault(key, []).append(row_number)
            continue
        index[key] = row_number

    return index, duplicates, new_rows, blank_rows

"""
Split test_docs.zip into per-org, per-doc-type zip files.
Output: PRANA/org_zips/ORG01_TechNova_Solutions/SALARY_SLIP.zip etc.

Each zip contains only PDFs for that org + that doc type.
OA Admin for Org01 uploads ONLY Org01 zips. Never cross-org.
"""

import zipfile, re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "PRANA" / "test_docs.zip"
OUT = Path(__file__).parent.parent.parent / "PRANA" / "org_zips"
OUT.mkdir(parents=True, exist_ok=True)

# filename pattern: ORG01_TechNova.../ORG01-EMP001_Name/02_SALARY_SLIP_2022-03.pdf
ORG_RE     = re.compile(r"^(ORG\d+_[^/]+)/")
DTYPE_RE   = re.compile(r"/\d+_([A-Z0-9_]+)_\d{4}-\d{2}\.pdf$")

writers: dict[tuple, zipfile.ZipFile] = {}
counts:  dict[tuple, int]             = {}

print(f"Reading {SRC} ...")

with zipfile.ZipFile(SRC) as src:
    for entry in src.infolist():
        if entry.is_dir():
            continue

        name = entry.filename
        org_m   = ORG_RE.search(name)
        dtype_m = DTYPE_RE.search(name)
        if not org_m or not dtype_m:
            print(f"  SKIP (no match): {name}")
            continue

        org_folder = org_m.group(1)          # e.g. ORG01_TechNova_Solutions_Pvt_Ltd
        doc_type   = dtype_m.group(1)        # e.g. SALARY_SLIP
        key        = (org_folder, doc_type)

        if key not in writers:
            org_out = OUT / org_folder
            org_out.mkdir(exist_ok=True)
            zip_path = org_out / f"{doc_type}.zip"
            writers[key] = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)
            counts[key]  = 0

        # Store with just employee/filename — strip the org prefix
        inner_path = "/".join(name.split("/")[1:])   # EMP001_Name/02_SALARY_SLIP_...pdf
        writers[key].writestr(inner_path, src.read(name))
        counts[key] += 1

# Close all writers
for zf in writers.values():
    zf.close()

# Summary
print("\nOutput:")
prev_org = None
total_zips = 0
total_docs = 0
for (org, dt), n in sorted(counts.items()):
    if org != prev_org:
        print(f"\n  {org}/")
        prev_org = org
    zip_kb = (OUT / org / f"{dt}.zip").stat().st_size // 1024
    print(f"    {dt}.zip  — {n} docs  ({zip_kb} KB)")
    total_zips += 1
    total_docs += n

print(f"\nTotal: {total_zips} zip files, {total_docs} documents")
print(f"Location: {OUT}")

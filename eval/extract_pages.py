"""Write the raw text of every PDF page, one JSON file per version, for build_eval.py.

Usage (from the project root): python -I eval/extract_pages.py data/raw eval/pages
Reads the six Claims Code PDFs named as in data/manifest.csv.
"""
import json, os, sys
import pymupdf

FILES = {"v1": "vcmi-ccp-v1.pdf", "v2": "vcmi-ccp-v2.pdf", "v2.1": "vcmi-ccp-v2.1.pdf",
         "v3.0": "vcmi-ccp-v3.pdf", "v3.1": "vcmi-ccp-v3.1.pdf", "v3.2": "vcmi-ccp-v3.2.pdf"}

raw_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
for v, name in FILES.items():
    doc = pymupdf.open(os.path.join(raw_dir, name))
    with open(os.path.join(out_dir, f"{v}.json"), "w", encoding="utf-8") as f:
        json.dump([page.get_text() for page in doc], f, ensure_ascii=False)
    print(f"{v}: {doc.page_count} pages")

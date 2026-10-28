"""Rename the catalog/schemas used by every file in dbx_to_prod (only if prod does not use `workspace`).

Usage (from the repo root):
    python3 dbx_to_prod/scripts/retarget.py --catalog prod_genai --docs-schema docs --perf-schema performance --dry-run
    python3 dbx_to_prod/scripts/retarget.py --catalog prod_genai --docs-schema docs --perf-schema performance

Rewrites SQL, notebooks, agent definitions and the app template in place. The Flask app and the
upload tool hard-code the same names; the script lists those lines so you can change them too.
"""
import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parent
APP_FILES = ["src/mariner_genai_dbx/config.py", "src/mariner_genai_dbx/performance_retrieval.py",
             "src/mariner_genai_dbx/coaching360.py", "simple_upload/app.py", ".env.example"]


def replacements(catalog, docs, perf):
    return [
        (r"/Volumes/workspace/default/", f"/Volumes/{catalog}/{docs}/"),
        (r"/Volumes/workspace/performance_test/", f"/Volumes/{catalog}/{perf}/"),
        # Coaching360 keeps its schema names (coaching360demo, c360_*); only the catalog moves.
        (r"/Volumes/workspace/coaching360demo/", f"/Volumes/{catalog}/coaching360demo/"),
        (r"\bworkspace\.(coaching360demo|c360_[a-z_]+)\b", f"{catalog}.\\1"),
        (r"\bworkspace\.default\b", f"{catalog}.{docs}"),
        (r"\bworkspace\.performance_test\b", f"{catalog}.{perf}"),
        (r"\bworkspace`\.`default\b", f"{catalog}`.`{docs}"),
        (r"\bworkspace`\.`performance_test\b", f"{catalog}`.`{perf}"),
        (r'CATALOG = "workspace"', f'CATALOG = "{catalog}"'),
        (r'f"\{CATALOG\}\.default"', f'f"{{CATALOG}}.{docs}"'),
        (r'f"\{CATALOG\}\.performance_test"', f'f"{{CATALOG}}.{perf}"'),
        (r"/Volumes/\{CATALOG\}/default/", f"/Volumes/{{CATALOG}}/{docs}/"),
        (r"/Volumes/\{CATALOG\}/performance_test/", f"/Volumes/{{CATALOG}}/{perf}/"),
        (r"CATALOG IF NOT EXISTS workspace;", f"CATALOG IF NOT EXISTS {catalog};"),
        (r"ON CATALOG workspace\b", f"ON CATALOG {catalog}"),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--docs-schema", default="default")
    parser.add_argument("--perf-schema", default="performance_test")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rules = replacements(args.catalog, args.docs_schema, args.perf_schema)
    targets = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in {".sql", ".py", ".json", ".md", ".template", ".yaml"}
               and "exports" not in p.parts and p.name != "retarget.py"]
    for path in sorted(targets):
        text = original = path.read_text()
        for pattern, value in rules:
            text = re.sub(pattern, value, text)
        if text != original:
            changes = sum(1 for a, b in zip(original.splitlines(), text.splitlines()) if a != b)
            print(f"{'would change' if args.dry_run else 'changed'} {path.relative_to(REPO)} ({changes} lines)")
            if not args.dry_run:
                path.write_text(text)
    print("\nApp files that also hard-code these names (edit them before deploying):")
    for rel in APP_FILES:
        path = REPO / rel
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"workspace\.(default|performance_test|coaching360demo|c360_)|/Volumes/workspace/", line):
                print(f"  {rel}:{number}: {line.strip()[:110]}")


if __name__ == "__main__":
    main()

import argparse
import csv
import re
from pathlib import Path


# ============================================================
# FILE NAME PATTERNS
# ============================================================

# Expected prefix:
#
# 005_*025*_
# 010_*100*_
# 100_*1000*_
#
# First 3 digits     = concurrent users
# Next 3 or 4 digits = total requests

PREFIX_PATTERN = re.compile(
    r"^(?P<users>\d{3})_(?P<requests>\d{3,4})_"
)

# Timestamp format:
#
# 20261015_091500

TIMESTAMP_PATTERN = re.compile(
    r"(?P<timestamp>\d{8}_\d{6})"
)


# ============================================================
# PARSE FILE NAME
# ============================================================

def parse_filename(filename):

    prefix_match = PREFIX_PATTERN.search(filename)

    if not prefix_match:
        return None

    timestamp_match = TIMESTAMP_PATTERN.search(filename)

    if not timestamp_match:
        return None

    users_text = prefix_match.group("users")
    requests_text = prefix_match.group("requests")

    users = int(users_text)
    requests = int(requests_text)

    # Keep prefix exactly as represented in the filename,
    # except for the final "_" separator.
    #
    # Example:
    # 005_*025*
    prefix = prefix_match.group(0).rstrip("_")

    timestamp = timestamp_match.group("timestamp")

    return {
        "prefix": prefix,
        "users": users,
        "requests": requests,
        "timestamp": timestamp
    }


# ============================================================
# READ SUMMARY TXT
# ============================================================

def read_summary_file(summary_path):

    summary = {}

    with open(
        summary_path,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            if ":" not in line:
                continue

            key, value = line.split(":", 1)

            key = key.strip()
            value = value.strip()

            if key and value:
                summary[key] = value

    return summary


# ============================================================
# CLEAN SUMMARY COLUMN NAMES
# ============================================================

def clean_column_name(name):

    name = name.strip().lower()

    name = name.replace("/", "_per_")

    name = name.replace("%", "percent")

    name = re.sub(
        r"[^a-z0-9]+",
        "_",
        name
    )

    return name.strip("_")


# ============================================================
# FIND COMPANION TXT FILE
# ============================================================

def find_summary_file(directory, file_info):

    prefix = file_info["prefix"]
    timestamp = file_info["timestamp"]

    matches = []

    for txt_file in directory.glob("*.txt"):

        txt_info = parse_filename(
            txt_file.name
        )

        if not txt_info:
            continue

        # Match using BOTH prefix and timestamp.
        #
        # This allows the same test configuration
        # to be run multiple times.

        if (
            txt_info["prefix"] == prefix
            and
            txt_info["timestamp"] == timestamp
        ):
            matches.append(txt_file)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:

        print(
            f"WARNING: Multiple TXT files found for "
            f"{prefix} / {timestamp}"
        )

        return matches[0]

    return None


# ============================================================
# PROCESS ONE CSV/TXT PAIR
# ============================================================

def process_csv(csv_path, directory):

    file_info = parse_filename(
        csv_path.name
    )

    if not file_info:

        print(
            f"SKIPPING: {csv_path.name}"
        )

        print(
            "  Filename does not match expected format."
        )

        return []


    print()
    print(
        "------------------------------------------------"
    )

    print(
        f"Processing CSV: {csv_path.name}"
    )

    print(
        f"Prefix:         {file_info['prefix']}"
    )

    print(
        f"Users:          {file_info['users']}"
    )

    print(
        f"Requests:       {file_info['requests']}"
    )

    print(
        f"Timestamp:      {file_info['timestamp']}"
    )


    # ========================================================
    # FIND SUMMARY FILE
    # ========================================================

    summary_file = find_summary_file(
        directory,
        file_info
    )

    summary_data = {}


    if summary_file:

        print(
            f"Summary TXT:    {summary_file.name}"
        )

        raw_summary = read_summary_file(
            summary_file
        )


        # Convert:
        #
        # Success rate
        #
        # into:
        #
        # summary_success_rate

        for key, value in raw_summary.items():

            clean_key = clean_column_name(
                key
            )

            summary_data[
                f"summary_{clean_key}"
            ] = value

    else:

        print(
            "WARNING: No companion TXT file found."
        )


    # ========================================================
    # READ CSV
    # ========================================================

    rows = []


    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)


        for row in reader:

            combined_row = {}


            # =================================================
            # SOURCE FILE INFORMATION
            # =================================================

            combined_row[
                "source_csv_file"
            ] = csv_path.name


            combined_row[
                "source_summary_file"
            ] = (
                summary_file.name
                if summary_file
                else ""
            )


            # =================================================
            # INFORMATION EXTRACTED FROM FILE NAME
            # =================================================

            combined_row[
                "file_prefix"
            ] = file_info["prefix"]


            combined_row[
                "file_timestamp"
            ] = file_info["timestamp"]


            combined_row[
                "test_users"
            ] = file_info["users"]


            combined_row[
                "test_total_requests"
            ] = file_info["requests"]


            # =================================================
            # ORIGINAL REQUEST-LEVEL CSV DATA
            # =================================================

            for key, value in row.items():

                combined_row[key] = value


            # =================================================
            # SUMMARY TXT DATA
            # =================================================

            for key, value in summary_data.items():

                combined_row[key] = value


            rows.append(
                combined_row
            )


    print(
        f"Rows loaded:     {len(rows)}"
    )


    return rows


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Combine Databricks stress-test CSV result files "
            "with their companion TXT summary files."
        )
    )


    parser.add_argument(
        "--dir",
        required=True,
        help=(
            "Directory containing the stress-test "
            "CSV and TXT files."
        )
    )


    parser.add_argument(
        "--output",
        default="combined_stress_test_results.csv",
        help=(
            "Output CSV filename. "
            "Default: combined_stress_test_results.csv"
        )
    )


    args = parser.parse_args()


    # ========================================================
    # VALIDATE DIRECTORY
    # ========================================================

    directory = Path(
        args.dir
    ).expanduser().resolve()


    if not directory.exists():

        raise SystemExit(
            f"Directory does not exist: {directory}"
        )


    if not directory.is_dir():

        raise SystemExit(
            f"Path is not a directory: {directory}"
        )


    print()
    print(
        "================================================"
    )

    print(
        " STRESS TEST RESULTS COMBINER"
    )

    print(
        "================================================"
    )

    print(
        f"Directory: {directory}"
    )


    # ========================================================
    # FIND CSV FILES
    # ========================================================

    csv_files = sorted(
        directory.glob("*.csv")
    )


    # Prevent the script from processing its own
    # previously generated output.

    csv_files = [
        file
        for file in csv_files
        if file.name != args.output
    ]


    if not csv_files:

        raise SystemExit(
            "No CSV files found."
        )


    print(
        f"CSV files found: {len(csv_files)}"
    )


    # ========================================================
    # PROCESS ALL FILE PAIRS
    # ========================================================

    all_rows = []

    files_processed = 0


    for csv_file in csv_files:

        rows = process_csv(
            csv_file,
            directory
        )


        if rows:

            all_rows.extend(
                rows
            )

            files_processed += 1


    if not all_rows:

        raise SystemExit(
            "No valid stress-test results were found."
        )


    # ========================================================
    # BUILD COLUMN LIST
    # ========================================================

    fieldnames = []


    for row in all_rows:

        for key in row.keys():

            if key not in fieldnames:

                fieldnames.append(
                    key
                )


    # ========================================================
    # WRITE COMBINED CSV
    # ========================================================

    output_path = (
        directory
        / args.output
    )


    with open(
        output_path,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )


        writer.writeheader()


        writer.writerows(
            all_rows
        )


    # ========================================================
    # FINISHED
    # ========================================================

    print()
    print(
        "================================================"
    )

    print(
        " COMPLETE"
    )

    print(
        "================================================"
    )


    print(
        f"CSV files processed: {files_processed}"
    )


    print(
        f"Total request rows:  {len(all_rows)}"
    )


    print()
    print(
        "Combined file:"
    )

    print(
        output_path
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
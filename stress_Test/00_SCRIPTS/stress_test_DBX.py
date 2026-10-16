import time
import uuid
import csv
import statistics

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from mariner_genai_dbx.bootstrap import create_supervisor_service
from mariner_genai_dbx.config import load_settings
from mariner_genai_dbx.models import ConversationHistory



# ============================================================
# TEST SETTINGS
# ============================================================

CONCURRENT_USERS = 10
TOTAL_REQUESTS = 20

QUESTION = (
    "Mandatory application routing directive: "
    "Call the Branch Operations specialist named "
    "mariner-policy-assistant subagent/tool now and wait for it "
    "to complete. Return the worker's final grounded answer and "
    "source information. Do not answer from general model knowledge. "
    "Employee question: What does the policy say about record retention?"
)


# ============================================================
# SAME TIMESTAMP FOR ALL OUTPUT FILES
# ============================================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

csv_file = f"databricks_stress_results_{timestamp}.csv"
summary_file = f"databricks_stress_summary_{timestamp}.txt"


# ============================================================
# CONNECT DIRECTLY TO DATABRICKS
# ============================================================

print()
print("Loading Databricks configuration...", flush=True)

settings = load_settings()

print("Creating Databricks Supervisor service...", flush=True)

service = create_supervisor_service(settings)

print("Databricks Supervisor service created.", flush=True)


# ============================================================
# SEND ONE REQUEST DIRECTLY TO SUPERVISOR
# ============================================================

def send_request(number):

    # Every simulated user gets a separate session
    session_id = f"stress-test-{uuid.uuid4()}"

    # No Flask conversation history
    history = ConversationHistory()

    start = time.perf_counter()

    try:

        result = service.answer(
            QUESTION,
            session_id,
            history
        )

        latency = time.perf_counter() - start

        return {
            "number": number,
            "status": "SUCCESS",
            "latency": round(latency, 3),
            "success": True,
            "session_id": session_id,
            "agents_used": str(result.agents_used),
            "error": ""
        }

    except Exception as e:

        latency = time.perf_counter() - start

        return {
            "number": number,
            "status": "ERROR",
            "latency": round(latency, 3),
            "success": False,
            "session_id": session_id,
            "agents_used": "",
            "error": str(e)[:1000]
        }


# ============================================================
# START TEST
# ============================================================

print()
print("==========================================")
print(" DATABRICKS DIRECT MULTI-AGENT STRESS TEST")
print("==========================================")
print(f"Concurrent users: {CONCURRENT_USERS}")
print(f"Total requests:   {TOTAL_REQUESTS}")
print(f"Timestamp:        {timestamp}")
print()

results = []

test_start = time.perf_counter()


# ============================================================
# EXECUTE CONCURRENT REQUESTS
# ============================================================

with ThreadPoolExecutor(
    max_workers=CONCURRENT_USERS
) as executor:

    futures = [
        executor.submit(
            send_request,
            i + 1
        )
        for i in range(TOTAL_REQUESTS)
    ]

    for future in as_completed(futures):

        result = future.result()

        results.append(result)

        print(
            f"Request {result['number']:03d} | "
            f"{result['status']:7} | "
            f"{result['latency']:.2f}s",
            flush=True
        )


# ============================================================
# CALCULATE RESULTS
# ============================================================

total_time = time.perf_counter() - test_start

successful = [
    r for r in results
    if r["success"]
]

failed = [
    r for r in results
    if not r["success"]
]

latencies = [
    r["latency"]
    for r in results
]


def percentile(values, p):

    values = sorted(values)

    index = int(
        (len(values) - 1) * p
    )

    return values[index]


average_latency = statistics.mean(latencies)

median_latency = statistics.median(latencies)

p95_latency = percentile(
    latencies,
    0.95
)

p99_latency = percentile(
    latencies,
    0.99
)

maximum_latency = max(latencies)

success_rate = (
    len(successful)
    / len(results)
    * 100
)

requests_per_second = (
    len(results)
    / total_time
)

requests_per_minute = (
    requests_per_second
    * 60
)


# ============================================================
# DISPLAY RESULTS
# ============================================================

print()
print("==========================================")
print(" RESULTS")
print("==========================================")

print(
    f"Total requests:        {len(results)}"
)

print(
    f"Successful:            {len(successful)}"
)

print(
    f"Failed:                {len(failed)}"
)

print(
    f"Success rate:          {success_rate:.1f}%"
)

print()

print(
    f"Average latency:       {average_latency:.2f}s"
)

print(
    f"Median latency:        {median_latency:.2f}s"
)

print(
    f"P95 latency:           {p95_latency:.2f}s"
)

print(
    f"P99 latency:           {p99_latency:.2f}s"
)

print(
    f"Maximum latency:       {maximum_latency:.2f}s"
)

print()

print(
    f"Total test time:       {total_time:.2f}s"
)

print(
    f"Requests / second:     {requests_per_second:.2f}"
)

print(
    f"Requests / minute:     {requests_per_minute:.2f}"
)


# ============================================================
# SAVE DETAILED CSV
# ============================================================

with open(
    csv_file,
    "w",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "number",
            "status",
            "latency",
            "success",
            "session_id",
            "agents_used",
            "error"
        ]
    )

    writer.writeheader()

    writer.writerows(results)


# ============================================================
# SAVE SUMMARY
# ============================================================

with open(
    summary_file,
    "w"
) as f:

    f.write(
        "Databricks Direct Multi-Agent Stress Test\n"
    )

    f.write(
        "==========================================\n\n"
    )

    f.write(
        f"Timestamp:          {timestamp}\n"
    )

    f.write(
        f"Concurrent users:   {CONCURRENT_USERS}\n"
    )

    f.write(
        f"Total requests:     {len(results)}\n"
    )

    f.write(
        f"Successful:         {len(successful)}\n"
    )

    f.write(
        f"Failed:             {len(failed)}\n"
    )

    f.write(
        f"Success rate:       {success_rate:.1f}%\n\n"
    )

    f.write(
        f"Average latency:    {average_latency:.2f}s\n"
    )

    f.write(
        f"Median latency:     {median_latency:.2f}s\n"
    )

    f.write(
        f"P95 latency:        {p95_latency:.2f}s\n"
    )

    f.write(
        f"P99 latency:        {p99_latency:.2f}s\n"
    )

    f.write(
        f"Maximum latency:    {maximum_latency:.2f}s\n\n"
    )

    f.write(
        f"Total test time:    {total_time:.2f}s\n"
    )

    f.write(
        f"Requests / second:  {requests_per_second:.2f}\n"
    )

    f.write(
        f"Requests / minute:  {requests_per_minute:.2f}\n"
    )


# ============================================================
# DISPLAY ERRORS
# ============================================================

if failed:

    print()
    print("ERRORS")
    print("------------------------------------------")

    for result in failed:

        print(
            f"Request {result['number']} | "
            f"{result['error']}"
        )


# ============================================================
# FINISHED
# ============================================================

print()
print("Files created:")

print(
    f"  {csv_file}"
)

print(
    f"  {summary_file}"
)
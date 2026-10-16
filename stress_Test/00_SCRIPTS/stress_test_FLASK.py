import requests
import time
import uuid
import statistics
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# SETTINGS
# ============================================================

URL = "http://127.0.0.1:8000/api/v1/chat"

CONCURRENT_USERS = 5
TOTAL_REQUESTS = 10
TIMEOUT = 180

QUESTION = "/policy What does the policy say about record retention?"

# Create ONE timestamp for this entire run
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

csv_file = f"stress_test_results_{timestamp}.csv"
summary_file = f"stress_test_summary_{timestamp}.txt"


# ============================================================
# SEND ONE REQUEST
# ============================================================

def send_request(number):

    payload = {
        "message": QUESTION,
        "conversationId": str(uuid.uuid4())
    }

    start = time.perf_counter()

    try:
        response = requests.post(
            URL,
            json=payload,
            timeout=TIMEOUT
        )

        latency = time.perf_counter() - start

        return {
            "number": number,
            "status": response.status_code,
            "latency": round(latency, 3),
            "success": response.status_code == 200,
            "error": None if response.ok else response.text[:300]
        }

    except Exception as e:

        latency = time.perf_counter() - start

        return {
            "number": number,
            "status": "ERROR",
            "latency": round(latency, 3),
            "success": False,
            "error": str(e)
        }


# ============================================================
# RUN STRESS TEST
# ============================================================

print("\nDatabricks Multi-Agent Stress Test")
print("-----------------------------------")
print(f"Concurrent users: {CONCURRENT_USERS}")
print(f"Total requests:   {TOTAL_REQUESTS}")
print(f"Endpoint:         {URL}")
print(f"Timestamp:        {timestamp}")
print()

results = []

test_start = time.perf_counter()

with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:

    futures = [
        executor.submit(send_request, i + 1)
        for i in range(TOTAL_REQUESTS)
    ]

    for future in as_completed(futures):

        result = future.result()
        results.append(result)

        print(
            f"Request {result['number']:03d} | "
            f"Status {result['status']} | "
            f"{result['latency']:.2f}s",
            flush=True
        )


# ============================================================
# CALCULATE RESULTS
# ============================================================

total_time = time.perf_counter() - test_start

successful = [r for r in results if r["success"]]
failed = [r for r in results if not r["success"]]

latencies = [r["latency"] for r in results]


def percentile(values, p):
    values = sorted(values)
    index = int((len(values) - 1) * p)
    return values[index]


average_latency = statistics.mean(latencies)
median_latency = statistics.median(latencies)
p95_latency = percentile(latencies, 0.95)
p99_latency = percentile(latencies, 0.99)
max_latency = max(latencies)

success_rate = len(successful) / len(results) * 100
requests_per_minute = len(results) / total_time * 60


# ============================================================
# DISPLAY RESULTS
# ============================================================

print("\n===================================")
print("RESULTS")
print("===================================")

print(f"Total requests:    {len(results)}")
print(f"Successful:        {len(successful)}")
print(f"Failed:            {len(failed)}")
print(f"Success rate:      {success_rate:.1f}%")

print()
print(f"Average latency:   {average_latency:.2f}s")
print(f"Median latency:    {median_latency:.2f}s")
print(f"P95 latency:       {p95_latency:.2f}s")
print(f"P99 latency:       {p99_latency:.2f}s")
print(f"Maximum latency:   {max_latency:.2f}s")

print()
print(f"Total test time:   {total_time:.2f}s")
print(f"Throughput:        {requests_per_minute:.2f} requests/min")


# ============================================================
# SAVE DETAILED RESULTS CSV
# ============================================================

with open(csv_file, "w", newline="") as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "number",
            "status",
            "latency",
            "success",
            "error"
        ]
    )

    writer.writeheader()
    writer.writerows(results)


# ============================================================
# SAVE SUMMARY TXT
# ============================================================

with open(summary_file, "w") as f:

    f.write("Databricks Multi-Agent Stress Test\n")
    f.write("===================================\n\n")

    f.write(f"Timestamp:          {timestamp}\n")
    f.write(f"Endpoint:           {URL}\n")
    f.write(f"Question:           {QUESTION}\n\n")

    f.write(f"Concurrent users:   {CONCURRENT_USERS}\n")
    f.write(f"Total requests:     {len(results)}\n")
    f.write(f"Successful:         {len(successful)}\n")
    f.write(f"Failed:             {len(failed)}\n")
    f.write(f"Success rate:       {success_rate:.1f}%\n\n")

    f.write(f"Average latency:    {average_latency:.2f}s\n")
    f.write(f"Median latency:     {median_latency:.2f}s\n")
    f.write(f"P95 latency:        {p95_latency:.2f}s\n")
    f.write(f"P99 latency:        {p99_latency:.2f}s\n")
    f.write(f"Maximum latency:    {max_latency:.2f}s\n\n")

    f.write(f"Total test time:    {total_time:.2f}s\n")
    f.write(f"Throughput:         {requests_per_minute:.2f} requests/min\n")


# ============================================================
# DONE
# ============================================================

print()
print("Files created:")
print(f"  {csv_file}")
print(f"  {summary_file}")
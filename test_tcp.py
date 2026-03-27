import os
from spiffe.workloadapi.workload_api_client import WorkloadApiClient

try:
    path = os.path.relpath("./infra/spire/sockets/workload_api.sock")
    path = path.replace("\\", "/")
    os.environ["SPIFFE_ENDPOINT_SOCKET"] = f"unix:{path}"
    with WorkloadApiClient() as client:
        print("SUCCESS RELATIVE")
except Exception as e:
    print(f"FAILED RELATIVE: {e}")

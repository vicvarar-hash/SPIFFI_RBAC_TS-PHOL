import os
import spiffe.workloadapi.workload_api_client as mod

original_target = mod.WorkloadApiClient._grpc_target

def patched_target(self, endpoint_socket: str) -> str:
    if "tcp://" in endpoint_socket:
        return endpoint_socket.replace("tcp://", "")
    return original_target(self, endpoint_socket)

mod.WorkloadApiClient._grpc_target = patched_target

os.environ["SPIFFE_ENDPOINT_SOCKET"] = "tcp://127.0.0.1:8082"

from spiffe.workloadapi.workload_api_client import WorkloadApiClient

try:
    with WorkloadApiClient() as client:
        ctx = client.fetch_x509_context()
        if ctx:
            print(f"SUCCESS: {ctx.default_svid.spiffe_id}")
        else:
            print("FAILED: no context")
except Exception as e:
    import traceback
    traceback.print_exc()

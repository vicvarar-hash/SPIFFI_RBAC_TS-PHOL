import os
import logging
from typing import Tuple, Optional

try:
    from spiffe.workloadapi.workload_api_client import WorkloadApiClient
    SPIFFE_AVAILABLE = True
except ImportError:
    SPIFFE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Sidecar mode paths (when SPIRE is bundled in the container)
SIDECAR_SOCKET = "/tmp/spire-agent/public/api.sock"
SIDECAR_BINARY = "/opt/spire/bin/spire-agent"
SIDECAR_SERVER_BINARY = "/opt/spire/bin/spire-server"
SIDECAR_SERVER_SOCKET = "/tmp/spire-server/private/api.sock"


def _is_sidecar_mode() -> bool:
    """Check if SPIRE is running as a sidecar (binaries + socket present)."""
    return os.path.exists(SIDECAR_SOCKET)


class SpiffeWorkloadService:
    """
    Interface to the SPIFFE Workload API.
    Supports two modes:
    - Sidecar: SPIRE server+agent run in the same container (cloud deployment)
    - Docker Compose: SPIRE runs in separate containers (local development)
    Falls back gracefully if SPIRE is unavailable.
    """
    
    @staticmethod
    def fetch_real_identity() -> Tuple[Optional[str], str]:
        """
        Returns:
            Tuple[spiffe_id, source_reason]
            If spiffe_id is None, UI should fall back to simulated mode.
        """
        import subprocess

        # Mode 1: Sidecar — use direct binary call against local socket
        if _is_sidecar_mode():
            try:
                result = subprocess.run(
                    [SIDECAR_BINARY, "api", "fetch", "x509",
                     "-socketPath", SIDECAR_SOCKET],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    if "no identity issued" in result.stderr:
                        return None, "SPIRE Agent running but no identity issued for this process"
                    return None, f"SPIRE sidecar fetch failed: {result.stderr.strip()}"
                
                for line in result.stdout.split('\n'):
                    if "SPIFFE ID:" in line:
                        return line.split("SPIFFE ID:")[1].strip(), "SPIRE Sidecar (Workload API)"
                return None, "SPIRE sidecar fetch succeeded but no SPIFFE ID found"
            except Exception as e:
                logger.error(f"Sidecar SPIRE fetch error: {e}")
                return None, f"SPIRE sidecar error: {str(e)}"

        # Mode 2: Docker Compose — call via docker exec
        if not SPIFFE_AVAILABLE:
            # Check if docker compose mode is possible
            pass
            
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            if not os.path.isdir(spire_dir):
                return None, "SPIRE not found (no sidecar socket, no infra/spire directory)"
            result = subprocess.run(
                ["docker", "compose", "exec", "spire-agent", 
                 "/opt/spire/bin/spire-agent", "api", "fetch", "x509", 
                 "-socketPath", "/opt/spire/sockets/workload_api.sock"],
                cwd=spire_dir, capture_output=True, text=True, timeout=15
            )
            
            if result.returncode != 0:
                if "no identity issued" in result.stderr:
                    return None, "SPIRE responded but no identity issued (is the agent selector valid?)"
                return None, f"SPIRE CLI fetch failed: {result.stderr.strip()}"
                
            for line in result.stdout.split('\n'):
                if "SPIFFE ID:" in line:
                    return line.split("SPIFFE ID:")[1].strip(), "SPIRE Workload API (Docker)"
            return None, "SPIRE fetch succeeded but no SPIFFE ID found"

        except Exception as e:
            logger.error(f"Error fetching SPIFFE Workload token: {e}")
            return None, f"SPIRE fetch crashed: {str(e)}"

    @staticmethod
    def fetch_full_svid_status() -> str:
        """Returns the raw output from the SPIRE Agent for debugging/display."""
        import subprocess
        
        # Sidecar mode
        if _is_sidecar_mode():
            try:
                result = subprocess.run(
                    [SIDECAR_BINARY, "api", "fetch", "x509",
                     "-socketPath", SIDECAR_SOCKET],
                    capture_output=True, text=True, timeout=10
                )
                return result.stdout if result.returncode == 0 else result.stderr
            except Exception as e:
                return f"Error connecting to SPIRE sidecar: {str(e)}"

        # Docker compose mode
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            if not os.path.isdir(spire_dir):
                return "SPIRE infrastructure not available"
            result = subprocess.run(
                ["docker", "compose", "exec", "spire-agent", 
                 "/opt/spire/bin/spire-agent", "api", "fetch", "x509", 
                 "-socketPath", "/opt/spire/sockets/workload_api.sock"],
                cwd=spire_dir, capture_output=True, text=True, timeout=15
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"Error connecting to SPIRE Agent: {str(e)}"

    @staticmethod
    def is_sidecar_active() -> bool:
        """Check if SPIRE sidecar is running (socket exists)."""
        return _is_sidecar_mode()

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker daemon is running and accessible."""
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def is_spire_running() -> bool:
        """Check if SPIRE is up (sidecar or Docker containers)."""
        if _is_sidecar_mode():
            return True
        import subprocess
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            if not os.path.isdir(spire_dir):
                return False
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=spire_dir, capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0 and "spire-server" in result.stdout
        except Exception:
            return False

    @staticmethod
    def deploy_spire() -> tuple[bool, list[str]]:
        """
        Deploy SPIRE infrastructure via Docker Compose (local dev mode).
        Returns (success, log_lines).
        """
        import subprocess
        import time
        logs = []
        spire_dir = os.path.join(os.getcwd(), "infra", "spire")

        if not os.path.isdir(spire_dir):
            return False, ["❌ infra/spire directory not found"]

        try:
            logs.append("🧹 Cleaning up existing SPIRE containers...")
            subprocess.run(["docker", "compose", "down", "-v"], cwd=spire_dir,
                           capture_output=True, timeout=30)

            logs.append("🚀 Starting SPIRE Server...")
            r = subprocess.run(["docker", "compose", "up", "-d", "spire-server"],
                               cwd=spire_dir, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                logs.append(f"❌ Failed to start server: {r.stderr.strip()}")
                return False, logs

            logs.append("⏳ Waiting for SPIRE Server to initialize (5s)...")
            time.sleep(5)

            logs.append("🔑 Generating join token for agent...")
            r = subprocess.run(
                ["docker", "compose", "exec", "spire-server",
                 "/opt/spire/bin/spire-server", "token", "generate",
                 "-spiffeID", "spiffe://demo.local/agent/spire_agent"],
                cwd=spire_dir, capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0:
                logs.append(f"❌ Token generation failed: {r.stderr.strip()}")
                return False, logs

            token = ""
            for line in r.stdout.split('\n'):
                if "Token:" in line:
                    token = line.split("Token:")[1].strip()
                    break
            if not token:
                logs.append("❌ Could not parse token from server output")
                return False, logs
            logs.append(f"✅ Token generated: {token[:8]}...")

            with open(os.path.join(spire_dir, ".env"), "w") as f:
                f.write(f"SPIRE_TOKEN={token}\n")
            logs.append("🚀 Starting SPIRE Agent...")
            r = subprocess.run(["docker", "compose", "up", "-d", "spire-agent"],
                               cwd=spire_dir, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                logs.append(f"❌ Failed to start agent: {r.stderr.strip()}")
                return False, logs

            logs.append("⏳ Waiting for agent to sync (3s)...")
            time.sleep(3)

            logs.append("📝 Registering workload identities...")
            workloads = [
                "spiffe://demo.local/agent/devops",
                "spiffe://demo.local/agent/incident",
                "spiffe://demo.local/agent/finance",
                "spiffe://demo.local/agent/research",
                "spiffe://demo.local/service/gateway",
                "spiffe://demo.local/service/security",
            ]
            for spiffe_id in workloads:
                subprocess.run(
                    ["docker", "compose", "exec", "spire-server",
                     "/opt/spire/bin/spire-server", "entry", "create",
                     "-spiffeID", spiffe_id,
                     "-parentID", "spiffe://demo.local/agent/spire_agent",
                     "-selector", "unix:uid:0"],
                    cwd=spire_dir, capture_output=True, timeout=15
                )
            logs.append(f"✅ Registered {len(workloads)} workload identities")
            logs.append("🎉 SPIRE environment deployed successfully!")
            return True, logs

        except subprocess.TimeoutExpired:
            logs.append("❌ Operation timed out — is Docker responsive?")
            return False, logs
        except Exception as e:
            logs.append(f"❌ Unexpected error: {str(e)}")
            return False, logs

    @staticmethod
    def stop_spire() -> tuple[bool, str]:
        """Stop SPIRE containers (Docker Compose mode only)."""
        import subprocess
        spire_dir = os.path.join(os.getcwd(), "infra", "spire")
        if not os.path.isdir(spire_dir):
            return False, "infra/spire directory not found"
        try:
            r = subprocess.run(["docker", "compose", "down", "-v"],
                               cwd=spire_dir, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return True, "SPIRE containers stopped"
            return False, r.stderr.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def register_spiffe_entry(spiffe_id: str, parent_id: str = "spiffe://demo.local/agent/spire_agent", selector: str = "unix:uid:0") -> Tuple[bool, str]:
        """Registers a new entry with the SPIRE Server."""
        import subprocess
        
        # Sidecar mode — use direct binary
        if _is_sidecar_mode() and os.path.exists(SIDECAR_SERVER_BINARY):
            try:
                result = subprocess.run(
                    [SIDECAR_SERVER_BINARY, "entry", "create",
                     "-spiffeID", spiffe_id,
                     "-parentID", parent_id,
                     "-selector", selector,
                     "-socketPath", SIDECAR_SERVER_SOCKET],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    logger.info(f"Registered {spiffe_id} in SPIRE Server (sidecar)")
                    return True, "Registration successful (sidecar)."
                return False, f"SPIRE registration failed: {result.stderr.strip()}"
            except Exception as e:
                return False, f"Sidecar registration error: {str(e)}"

        # Docker compose mode
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            if not os.path.isdir(spire_dir):
                return False, "SPIRE infrastructure not found"
            result = subprocess.run(
                ["docker", "compose", "exec", "spire-server", 
                 "/opt/spire/bin/spire-server", "entry", "create",
                 "-spiffeID", spiffe_id,
                 "-parentID", parent_id,
                 "-selector", selector],
                cwd=spire_dir, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                logger.info(f"Registered {spiffe_id} in SPIRE Server")
                return True, "Registration successful."
            else:
                logger.error(f"Failed to register {spiffe_id} in SPIRE: {result.stderr}")
                return False, f"SPIRE registration failed: {result.stderr.strip()}"
        except Exception as e:
            return False, f"Error calling registration CLI: {str(e)}"


import os
import logging
from typing import Tuple, Optional

try:
    from spiffe.workloadapi.workload_api_client import WorkloadApiClient
    SPIFFE_AVAILABLE = True
except ImportError:
    SPIFFE_AVAILABLE = False

logger = logging.getLogger(__name__)

class SpiffeWorkloadService:
    """
    Interface to the SPIFFE Workload API.
    Attempts to retrieve a cryptographic identity from a local SPIRE agent.
    Falls back gracefully if SPIRE is unavailable or the pyspiffe library is missing.
    """
    
    @staticmethod
    def fetch_real_identity() -> Tuple[Optional[str], str]:
        """
        Returns:
            Tuple[spiffe_id, source_reason]
            If spiffe_id is None, UI should fall back to simulated mode.
        """
        if not SPIFFE_AVAILABLE:
            return None, "pyspiffe library not installed"
            
        import subprocess
        import sys
        
        # Execute the Spiffe CLI inside the agent container to securely fetch the X.509 context
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            result = subprocess.run(
                [
                    "docker", "compose", "exec", "spire-agent", 
                    "/opt/spire/bin/spire-agent", "api", "fetch", "x509", 
                    "-socketPath", "/opt/spire/sockets/workload_api.sock"
                ],
                cwd=spire_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if "no identity issued" in result.stderr:
                    return None, "SPIRE responded but no identity issued (is the agent selector valid?)"
                return None, f"SPIRE CLI fetch failed: {result.stderr.strip()}"
                
            # Parse the CLI output for the SPIFFE ID. 
            # Format: SPIFFE ID:      spiffe://demo.local/agent/devops
            spiffe_id = None
            for line in result.stdout.split('\n'):
                if "SPIFFE ID:" in line:
                    spiffe_id = line.split("SPIFFE ID:")[1].strip()
                    break
                    
            if spiffe_id:
                return spiffe_id, "SPIRE Workload API"
            else:
                return None, "SPIRE fetch succeeded but no SPIFFE ID found"

        except Exception as e:
            logger.error(f"Error fetching SPIFFE Workload token: {e}")
            return None, f"SPIRE fetch crashed: {str(e)}"

    @staticmethod
    def fetch_full_svid_status() -> str:
        """
        Returns the raw output from the SPIRE Agent for debugging/display purposes.
        """
        import subprocess
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            result = subprocess.run(
                [
                    "docker", "compose", "exec", "spire-agent", 
                    "/opt/spire/bin/spire-agent", "api", "fetch", "x509", 
                    "-socketPath", "/opt/spire/sockets/workload_api.sock"
                ],
                cwd=spire_dir,
                capture_output=True,
                text=True
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"Error connecting to SPIRE Agent: {str(e)}"

    @staticmethod
    def register_spiffe_entry(spiffe_id: str, parent_id: str = "spiffe://demo.local/agent/spire_agent", selector: str = "unix:uid:0") -> Tuple[bool, str]:
        """
        Registers a new entry with the SPIRE Server.
        """
        import subprocess
        try:
            spire_dir = os.path.join(os.getcwd(), "infra", "spire")
            result = subprocess.run(
                [
                    "docker", "compose", "exec", "spire-server", 
                    "/opt/spire/bin/spire-server", "entry", "create",
                    "-spiffeID", spiffe_id,
                    "-parentID", parent_id,
                    "-selector", selector
                ],
                cwd=spire_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Registered {spiffe_id} in SPIRE Server")
                return True, "Registration successful."
            else:
                logger.error(f"Failed to register {spiffe_id} in SPIRE: {result.stderr}")
                return False, f"SPIRE registration failed: {result.stderr.strip()}"
        except Exception as e:
            return False, f"Error calling registration CLI: {str(e)}"

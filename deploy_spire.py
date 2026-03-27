import os
import subprocess
import time

spire_dir = os.path.join(os.path.dirname(__abspath__), "infra", "spire") if "__abspath__" in globals() else os.path.join(os.getcwd(), "infra", "spire")

print("1. Cleaning up existing SPIRE containers...")
subprocess.run(["docker", "compose", "down", "-v"], cwd=spire_dir)

print("2. Starting SPIRE Server...")
subprocess.run(["docker", "compose", "up", "-d", "spire-server"], cwd=spire_dir)

print("Waiting 5 seconds for SPIRE Server to initialize...")
time.sleep(5)

print("3. Generating Join Token for Agent...")
result = subprocess.run(
    ["docker", "compose", "exec", "spire-server", "/opt/spire/bin/spire-server", "token", "generate", "-spiffeID", "spiffe://demo.local/agent/spire_agent"],
    cwd=spire_dir, capture_output=True, text=True
)

if result.returncode != 0:
    print(f"Failed to generate token: {result.stderr}")
    exit(1)

# Parse output e.g. "Token: 3e8a...5b11"
token = ""
for line in result.stdout.split('\n'):
    if "Token:" in line:
        token = line.split("Token:")[1].strip()
        break

if not token:
    print(f"Could not parse token from output: {result.stdout}")
    exit(1)

print(f"Token generated: {token[:8]}...")

print("4. Writing .env file for docker-compose...")
with open(os.path.join(spire_dir, ".env"), "w") as f:
    f.write(f"SPIRE_TOKEN={token}\n")

print("5. Starting SPIRE Agent...")
subprocess.run(["docker", "compose", "up", "-d", "spire-agent"], cwd=spire_dir)

print("Waiting 3 seconds for Agent to sync...")
time.sleep(3)

print("6. Registering Workloads...")
try:
    if os.path.exists(os.path.join(spire_dir, "register_workloads.sh")):
        # We need to run it via bash or manually execute the entries
        # Let's just manually run the entry commands to be cross-platform
        commands = [
            ["-spiffeID", "spiffe://demo.local/agent/devops", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
            ["-spiffeID", "spiffe://demo.local/agent/incident", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
            ["-spiffeID", "spiffe://demo.local/agent/finance", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
            ["-spiffeID", "spiffe://demo.local/agent/research", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
            ["-spiffeID", "spiffe://demo.local/service/gateway", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
            ["-spiffeID", "spiffe://demo.local/service/security", "-parentID", "spiffe://demo.local/agent/spire_agent", "-selector", "unix:uid:0"],
        ]
        
        for args in commands:
            cmd = ["docker", "compose", "exec", "spire-server", "/opt/spire/bin/spire-server", "entry", "create"] + args
            subprocess.run(cmd, cwd=spire_dir, stdout=subprocess.DEVNULL)
            
        print("Workloads registered successfully!")
except Exception as e:
    print(f"Warning running registration cmds natively: {e}")

print("✅ SPIRE Environment Deployed Successfully!")

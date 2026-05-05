import streamlit as st
import os
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas
from app.ui.home import render_home
from app.ui.astra_explorer import render_astra_explorer
from app.ui.mcp_explorer import render_mcp_explorer
from app.ui.prediction_lab import render_prediction_lab
from app.ui.policy_studio import render_policy_studio
from app.ui.experiment_lab import render_experiment_lab

# Page configuration
st.set_page_config(
    page_title="PALADIN | Policy-Aware Layered Agentic Decision Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load data with caching
@st.cache_data
def get_data():
    astra_path = os.path.join("datasets", "astra_03_tools.json")
    mcp_dir = "mcp_servers"
    
    tasks = load_astra_dataset(astra_path)
    personas, mcp_errors = load_mcp_personas(mcp_dir)
    
    return tasks, personas, mcp_errors

# Initialize session state
if 'tasks' not in st.session_state:
    tasks, personas, mcp_errors = get_data()
    st.session_state.tasks = tasks
    st.session_state.personas = personas
    st.session_state.mcp_errors = mcp_errors

tasks = st.session_state.tasks
personas = st.session_state.personas
mcp_errors = st.session_state.mcp_errors

# Sidebar navigation
st.sidebar.title("🛡️ PALADIN")
st.sidebar.caption("Policy-Aware Layered Agentic Decision Intelligence")
st.sidebar.markdown("---")

selection = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Home / Overview",
        "🛡️ Policy Studio",
        "🤖 MCP Domain Explorer",
        "🔍 ASTRA Task Explorer",
        "🔮 Prediction Lab",
        "🧪 Experiment Lab",
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Settings")
default_key = os.environ.get("OPENAI_API_KEY", "")
api_key = st.sidebar.text_input("OpenAI API Key", value=default_key, type="password")
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key

st.sidebar.markdown("---")
st.sidebar.info(
    """
    **PALADIN v3.0**
    - Layered Governance (RBAC/ABAC/TS-PHOL)
    - Capability-Aware LLM Inference
    - Experiment Framework
    - Policy Studio Configuration
    """
)

# Main content
if selection == "🏠 Home / Overview":
    render_home(tasks, personas)
elif selection == "🛡️ Policy Studio":
    render_policy_studio()
elif selection == "🤖 MCP Domain Explorer":
    render_mcp_explorer(personas)
elif selection == "🔍 ASTRA Task Explorer":
    render_astra_explorer(tasks, personas)
elif selection == "🔮 Prediction Lab":
    render_prediction_lab(tasks, personas)
elif selection == "🧪 Experiment Lab":
    render_experiment_lab(tasks, personas)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("© 2026 PALADIN Research Tool")

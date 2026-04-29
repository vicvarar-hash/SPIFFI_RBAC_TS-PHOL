import streamlit as st
import os
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas
from app.ui.home import render_home
from app.ui.astra_explorer import render_astra_explorer
from app.ui.mcp_explorer import render_mcp_explorer
from app.ui.prediction_lab import render_prediction_lab
from app.ui.health import render_health
from app.ui.policy_studio import render_policy_studio
from app.ui.experiment_lab import render_experiment_lab

# Page configuration
st.set_page_config(
    page_title="SPIFFI_RBACK_TS-PHOL | Iteration 2.1",
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
st.sidebar.title("🛡️ SPIFFI RBACK")
st.sidebar.markdown("---")

selection = st.sidebar.radio(
    "Navigation",
    ["🏠 Home / Overview", "🔍 ASTRA Task Explorer", "🤖 MCP Persona Explorer", "🔮 Prediction Lab", "🧪 Experiment Lab", "🛡️ Policy Studio", "🏥 Data Health / Validation"]
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
    **Iteration 2.1: Dual-Mode**
    - LLM-ResM (Selection)
    - Validation (Precursor)
    - Parallel Reasoning Panels
    - ASTRA Candidate Display
    """
)

# Main content
if selection == "🏠 Home / Overview":
    render_home(tasks, personas)
elif selection == "🔍 ASTRA Task Explorer":
    render_astra_explorer(tasks)
elif selection == "🤖 MCP Persona Explorer":
    render_mcp_explorer(personas)
elif selection == "🔮 Prediction Lab":
    render_prediction_lab(tasks, personas)
elif selection == "🧪 Experiment Lab":
    render_experiment_lab(tasks, personas)
elif selection == "🛡️ Policy Studio":
    render_policy_studio()
elif selection == "🏥 Data Health / Validation":
    render_health(tasks, personas, mcp_errors)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("© 2026 SPIFFI_RBACK_TS-PHOL Research Tool")

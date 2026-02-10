"""
Dashboard utility functions - data helpers, hierarchical lookups, and display utilities.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from config import PROJECT_ID

# Theme A colors (Pink/Purple based)
THEME_A_COLORS = {
    'primary': '#A66081',
    'secondary': '#C58392',
    'light': '#F1E0E4',
    'dark': '#8B4D6B',
    'accent': '#E8B4CC'
}

# Theme B colors (Blue based)
THEME_B_COLORS = {
    'primary': '#0077B6',    # Star Command Blue
    'secondary': '#48CAE4',  # Sky Blue
    'light': '#CAF0F8',      # Columbia Blue (Very Light)
    'dark': '#023E8A',       # Royal Blue
    'accent': '#90E0EF'      # Light Cyan
}

# Default to Theme A
PROJECT_COLORS = THEME_A_COLORS


def get_ram_usage():
    """Gets the current RAM usage for both local (macOS/Windows) and cloud (Linux)."""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        mb_value = memory_info.rss / 1024 / 1024
        return mb_value
    except ImportError:
        # Fallback to Linux method if psutil not available
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb_value = int(line.split()[1])
                        mb_value = kb_value / 1024
                        return mb_value
            return 0.0
        except:
            return 0.0
    except Exception:
        return 0.0


def display_system_health():
    """Display system health metrics in sidebar with history"""
    try:
        import psutil
        import time
        
        # Initialize history in session state
        if 'health_history' not in st.session_state:
            st.session_state.health_history = {
                'timestamps': [],
                'ram': [],
                'cpu': []
            }
        
        # Memory Usage
        process_ram = get_ram_usage() # MB
        system_mem = psutil.virtual_memory()
        total_ram_mb = system_mem.total / 1024 / 1024
        
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=0.01) # Reduced interval to minimize blocking
        cpu_count = psutil.cpu_count(logical=True)
        
        # Update history (keep last 50 points)
        current_time = datetime.now().strftime('%H:%M:%S')
        history = st.session_state.health_history
        history['timestamps'].append(current_time)
        history['ram'].append(process_ram)
        history['cpu'].append(cpu_percent)
        
        if len(history['timestamps']) > 20:
            history['timestamps'].pop(0)
            history['ram'].pop(0)
            history['cpu'].pop(0)

        # Display in Expander at bottom
        with st.sidebar.expander("🖥️ System Health", expanded=False):
            
            # 1. RAM Display
            ram_percent = (process_ram / total_ram_mb) * 100
            ram_color = "green"
            if ram_percent > 75: ram_color = "red"
            elif ram_percent > 50: ram_color = "orange"
            
            # Format: 1.3 GB / 32.0 GB
            proc_ram_str = f"{process_ram/1024:.1f} GB" if process_ram > 1000 else f"{process_ram:.0f} MB"
            total_ram_str = f"{total_ram_mb/1024:.1f} GB"
            
            st.markdown(f"**RAM:** :{ram_color}[{proc_ram_str}] / {total_ram_str}")
            st.progress(min(ram_percent / 100, 1.0))
            
            # 2. CPU Display
            cpu_color = "green"
            if cpu_percent > 80: cpu_color = "red"
            elif cpu_percent > 50: cpu_color = "orange"
            
            st.markdown(f"**CPU:** :{cpu_color}[{cpu_percent}%] (of {cpu_count} Cores)")
            st.progress(cpu_percent / 100)
            
            # 3. Query Performance
            if 'last_query_duration' in st.session_state:
                duration = st.session_state['last_query_duration']
                st.markdown(f"**Last Query Time:** {duration:.2f} s")
            
            if 'last_processing_duration' in st.session_state:
                proc_duration = st.session_state['last_processing_duration']
                st.markdown(f"**Last Processing Time:** {proc_duration:.2f} s")

            # 4. Historical Plot
            if len(history['ram']) > 1:
                st.caption("📈 Resource Usage Over Time")
                
                # Create a small dataframe for plotting
                chart_data = pd.DataFrame({
                    'RAM (MB)': history['ram'],
                    'CPU (%)': history['cpu']
                })
                
                st.line_chart(chart_data, height=150)

            # 4. Controls
            if process_ram > 1500:
                st.error("⚠️ High Memory Usage!")
            
            if st.button("🗑️ Clear Cache & GC", key="sidebar_health_clear_btn"):
                st.cache_data.clear()
                import gc
                gc.collect()
                st.rerun()
                
    except Exception as e:
        st.sidebar.warning(f"Health monitoring unavailable: {str(e)}")


def safe_dataframe_display(df, **kwargs):
    """Safely display a dataframe by converting all columns to strings to prevent PyArrow serialization issues"""
    if df.empty:
        st.info("No data to display.")
        return

    # Create a copy to avoid modifying the original
    safe_df = df.copy()

    # Convert all columns to strings to prevent mixed-type serialization issues
    for col in safe_df.columns:
        safe_df[col] = safe_df[col].astype(str)

    st.dataframe(safe_df, **kwargs)


@st.cache_data(ttl=3600)  # Cache timestamp conversions for 1 hour
def convert_unix_to_datetime(timestamp):
    """Convert UNIX timestamp (UTC) to IST datetime with caching for performance.
    
    UNIX timestamps are always in UTC. This function converts them to IST (UTC+5:30)
    to ensure consistent date attribution regardless of server timezone.
    """
    if not timestamp:
        return None


    try:
        from datetime import timezone
        
        # Default timezone offset (can be configured via env var if needed)
        # Using UTC+5:30 as default
        target_tz = timezone(timedelta(hours=5, minutes=30))
        
        IST = target_tz
        
        if isinstance(timestamp, (int, float)):
            # UNIX timestamps are UTC - convert to UTC-aware datetime first
            if timestamp > 1000000000000:
                utc_dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            else:
                utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            # Convert to IST and return as naive datetime (for compatibility)
            ist_dt = utc_dt.astimezone(IST)
            return ist_dt.replace(tzinfo=None)

        # Handle string timestamps
        result = pd.to_datetime(timestamp, errors='coerce')
        if pd.isna(result):
            return None
        return result
    except (ValueError, OSError, OverflowError):
        return None


def clean_emoji_text(text):
    """Remove emojis from text for better processing"""
    import re
    if not text:
        return ''
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', str(text))


def check_kmc_stability(baby):
    """Check if baby is unstable for KMC based on updated criteria"""
    # Check for instability indicators
    instability_indicators = [
        baby.get('oxygenTherapy') == True,
        baby.get('onOxygen') == True,
        baby.get('mechanicalVentilation') == True,
        baby.get('onVentilator') == True,
        baby.get('sepsis') == True,
        baby.get('jaundice') == True,
        baby.get('hypoglycemia') == True,
        baby.get('hypothermia') == True,
        baby.get('apnea') == True,
        baby.get('feedingDifficulty') == True,
        baby.get('lethargy') == True,
        baby.get('seizures') == True,
    ]
    
    # Check birth weight < 1500g
    birth_weight = baby.get('birthWeight') or baby.get('weight')
    if birth_weight:
        try:
            if float(birth_weight) < 1500:
                instability_indicators.append(True)
        except (ValueError, TypeError):
            pass
    
    if any(instability_indicators):
        return 'unstable'
    return 'stable'


# --- Hierarchical data access helpers ---

def get_prioritized_discharge_weight(baby, matching_discharge):
    """Get discharge weight using hierarchical approach: discharges → baby → babyBackUp collections"""
    discharge_weight = 'N/A'

    # STEP 1: Check discharges collection first (highest priority)
    if matching_discharge:
        discharge_weight = matching_discharge.get('dischargeWeight', 'N/A')

    # STEP 2: If not found, check the baby record for discharge weight
    if discharge_weight == 'N/A':
        discharge_weight = baby.get('dischargeWeight', 'N/A')

    return discharge_weight


def get_prioritized_discharge_temperature(baby, matching_discharge):
    """Get discharge temperature using hierarchical approach: discharges → baby → babyBackUp collections"""
    discharge_temp = 'N/A'

    # STEP 1: Check discharges collection first (highest priority) - dischargeTemperature
    if matching_discharge:
        discharge_temp = matching_discharge.get('dischargeTemperature', 'N/A')

    # STEP 2: If not found, check the baby record for babyTemperatureDischarge2
    if discharge_temp == 'N/A':
        discharge_temp = baby.get('babyTemperatureDischarge2', 'N/A')

    return discharge_temp


def get_prioritized_discharge_rr(baby, matching_discharge):
    """Get discharge respiratory rate using hierarchical approach: discharge → baby → babyBackUp collections"""
    discharge_rr = 'N/A'

    # STEP 1: Check discharges collection first (highest priority) - dischargeRR
    if matching_discharge:
        discharge_rr = matching_discharge.get('dischargeRR', 'N/A')

    # STEP 2: If not found, check the baby record for babyRRdischarge
    if discharge_rr == 'N/A':
        discharge_rr = baby.get('babyRRdischarge', 'N/A')

    return discharge_rr


def get_prioritized_feed_mode(baby, matching_discharge):
    """Get feed mode using hierarchical approach: discharge → baby → babyBackUp collections"""
    feed_mode = 'N/A'

    # STEP 1: Check discharges collection first (highest priority) - feedMode
    if matching_discharge:
        feed_mode = matching_discharge.get('feedMode', 'N/A')

    # STEP 2: If not found, check the baby record for whatFeedMode
    if feed_mode == 'N/A':
        feed_mode = baby.get('whatFeedMode', 'N/A')

    return feed_mode


def get_prioritized_baby_health(baby, matching_discharge):
    """Get baby health/danger signs using hierarchical approach: discharge → baby → babyBackUp collections"""
    baby_health = 'N/A'

    # STEP 1: Check discharges collection first (highest priority) - dischargeDangerSigns
    if matching_discharge:
        baby_health = matching_discharge.get('dischargeDangerSigns', 'N/A')

    # STEP 2: If not found, check the baby record for howsBabyHealth
    if baby_health == 'N/A':
        baby_health = baby.get('howsBabyHealth', 'N/A')

    return baby_health


def get_prioritized_critical_reasons(baby, matching_discharge):
    """Get critical reasons using hierarchical approach: discharge → baby → babyBackUp collections"""
    critical_reasons = 'N/A'

    # STEP 1: Check discharges collection first (highest priority)
    if matching_discharge:
        critical_reasons = matching_discharge.get('criticalReasons', 'N/A')

    # STEP 2: If not found, check the baby record for criticalReasons
    if critical_reasons == 'N/A':
        critical_reasons = baby.get('criticalReasons', 'N/A')

    return critical_reasons


def get_prioritized_discharge_reason(baby, matching_discharge):
    """Get discharge reason using hierarchical approach: discharge → baby → babyBackUp collections"""
    discharge_reason = 'N/A'

    # STEP 1: Check discharges collection first (highest priority) - dischargeReason
    if matching_discharge:
        discharge_reason = matching_discharge.get('dischargeReason', 'N/A')

    # STEP 2: If not found, check the baby record for dischargeReason
    if discharge_reason == 'N/A':
        discharge_reason = baby.get('dischargeReason', 'N/A')

    return discharge_reason


def get_hierarchical_discharge_date(baby, discharge_data):
    """Get discharge date using hierarchical approach: discharges → baby → babyBackUp collections"""
    baby_uid = baby.get('UID')
    discharge_date = None

    # STEP 1: Check discharges collection first (highest priority)
    if discharge_data:
        for discharge in discharge_data:
            if discharge.get('UID') == baby_uid:
                discharge_date = convert_unix_to_datetime(discharge.get('dischargeDate'))
                if discharge_date:
                    return discharge_date

    # STEP 2: Check baby record for discharge date
    if baby.get('discharged'):
        discharge_date = convert_unix_to_datetime(baby.get('lastDischargeDate') or baby.get('dischargeDate'))
        if discharge_date:
            return discharge_date

    # STEP 3: No discharge date found
    return None


def get_hierarchical_discharge_info(baby, discharge_data):
    """Get discharge date and weight using hierarchical approach: discharges → baby → babyBackUp"""
    baby_uid = baby.get('UID')
    discharge_date = None
    discharge_weight = None

    # STEP 1: Check discharges collection first
    if discharge_data:
        for discharge in discharge_data:
            if discharge.get('UID') == baby_uid:
                discharge_date = convert_unix_to_datetime(discharge.get('dischargeDate'))
                discharge_weight = discharge.get('dischargeWeight')
                if discharge_date:
                    return discharge_date, discharge_weight

    # STEP 2: Check baby record
    if baby.get('discharged'):
        discharge_date = convert_unix_to_datetime(baby.get('lastDischargeDate') or baby.get('dischargeDate'))
        discharge_weight = baby.get('dischargeWeight')

    return discharge_date, discharge_weight


def categorize_discharge(record, source):
    """Categorize discharge based on collection source with hierarchical logic for all three collections"""

    if source == 'discharges':
        # From discharges collection, use dischargeStatus and dischargeType
        discharge_status = record.get('dischargeStatus', '').lower()
        discharge_type = record.get('dischargeType', '').lower()

        # Critical and sent home: dischargeStatus = critical and dischargeType = home
        if discharge_status == 'critical' and discharge_type == 'home':
            return 'critical_home'

        # Stable and sent home: dischargeStatus = stable and dischargeType = home
        elif discharge_status == 'stable' and discharge_type == 'home':
            return 'stable_home'

        # Critical and referred: dischargeStatus = critical and dischargeType = referred
        elif discharge_status == 'critical' and discharge_type == 'referred':
            return 'critical_referred'

        # Died: dischargeType = died
        elif discharge_type == 'died':
            return 'died'
        else:
            return 'other'

    elif source == 'baby':
        # From baby collection, use lastDischargeStatus and lastDischargeType (similar to discharges collection logic)
        last_discharge_status = record.get('lastDischargeStatus', '').lower()
        last_discharge_type = record.get('lastDischargeType', '').lower()

        # Critical and sent home: lastDischargeStatus = critical and lastDischargeType = home
        if last_discharge_status == 'critical' and last_discharge_type == 'home':
            return 'critical_home'

        # Stable and sent home: lastDischargeStatus = stable and lastDischargeType = home
        elif last_discharge_status == 'stable' and last_discharge_type == 'home':
            return 'stable_home'

        # Critical and referred: lastDischargeStatus = critical and lastDischargeType = referred
        elif last_discharge_status == 'critical' and last_discharge_type == 'referred':
            return 'critical_referred'

        # Died: lastDischargeType = died
        elif last_discharge_type == 'died':
            return 'died'
        else:
            return 'other'
            
    elif source == 'babyBackUp':
        # From babyBackUp collection, same logic as baby
        last_discharge_status = record.get('lastDischargeStatus', '').lower()
        last_discharge_type = record.get('lastDischargeType', '').lower()

        if last_discharge_status == 'critical' and last_discharge_type == 'home':
            return 'critical_home'
        elif last_discharge_status == 'stable' and last_discharge_type == 'home':
            return 'stable_home'
        elif last_discharge_status == 'critical' and last_discharge_type == 'referred':
            return 'critical_referred'
        elif last_discharge_type == 'died':
            return 'died'
        else:
            return 'other'

    return 'other'

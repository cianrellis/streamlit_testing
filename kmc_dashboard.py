import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from config import PROJECT_ID, USE_FAKE_DATA

# --- Import from refactored modules ---
# --- Import from refactored modules ---
from utils.dashboard_utils import (
    PROJECT_COLORS,
    get_ram_usage,
    display_system_health,
    safe_dataframe_display,
    convert_unix_to_datetime,
    check_kmc_stability,
    clean_emoji_text,
    get_prioritized_discharge_weight,
    get_prioritized_discharge_temperature,
    get_prioritized_discharge_rr,
    get_prioritized_feed_mode,
    get_prioritized_baby_health,
    get_prioritized_critical_reasons,
    get_prioritized_discharge_reason,
    get_hierarchical_discharge_date,
    get_hierarchical_discharge_info,
    categorize_discharge,
)

from utils.dashboard_firebase import (
    initialize_firebase,
    load_collection_with_retry,
    load_query_with_retry,
    load_filtered_data_from_firebase,
    load_filtered_followup_data,
    load_firebase_data,
    get_db_counts,
)

from utils.dashboard_metrics import (
    calculate_registration_timeliness,
    calculate_kmc_initiation_metrics,
    calculate_average_kmc_by_location,
    calculate_discharge_outcomes,
    calculate_followup_metrics,
    calculate_hospital_stay_duration,
    calculate_death_rates,
    calculate_daily_kmc_analysis,
)



from utils.dashboard_tabs import (
    render_overview_tab,
    render_clinical_kpis_tab,
    render_mortality_tab,
    render_daily_kmc_tab,
    render_nurses_tab,
    render_sandbox_tab,
)



# Determine titles based on project ID
PAGE_TITLE = "KMC Dashboard"
HEADER_TITLE = "KMC Dashboard"

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon="👶",
    layout="wide",
    initial_sidebar_state="expanded"
)

def _filter_data(baby_data, start_date, end_date, selected_hospitals, selected_locations):
    """Optimized cached filtering function to prevent recalculating filters for same parameters"""
    try:
        filtered_data = []

        # Pre-convert hospital list to set for O(1) lookup
        hospital_set = set(selected_hospitals) if selected_hospitals else set()
        location_set = set(selected_locations) if selected_locations else set()

        # Skip date filtering if no date range specified
        skip_date_filter = not (start_date and end_date)

        for baby in baby_data:
            # Fast hospital filtering first (most selective)
            if hospital_set:
                hospital = baby.get('hospitalName', '').strip()
                if hospital not in hospital_set:
                    continue

            # Fast location filtering
            if location_set:
                location = baby.get('currentLocationOfBaby', '').strip()
                if location not in location_set:
                    continue

            # Date filtering (most expensive, do last)
            if not skip_date_filter:
                date_of_birth = baby.get('dateOfBirth')
                if date_of_birth:
                    try:
                        birth_dt = convert_unix_to_datetime(date_of_birth)
                        if birth_dt is None:
                            continue
                        birth_date = birth_dt.date()
                        if not (start_date <= birth_date <= end_date):
                            continue
                    except (ValueError, AttributeError, TypeError):
                        continue

            filtered_data.append(baby)

        return filtered_data
    except Exception as e:
        st.error(f"Error filtering data: {str(e)}")
        return []

@st.cache_data(show_spinner=False, ttl=900, max_entries=20)
@st.cache_data(show_spinner=False, ttl=900, max_entries=20)
# @st.cache_data(show_spinner=False, ttl=60, max_entries=20)  # DISABLED FOR DEBUGGING
def calculate_critical_reason_classification(discharge_data):
    """Classify babies based on criticalReason field from discharges collection only"""

    # Process discharges collection criticalReasons only
    discharge_processed_uids = set()
    discharge_critical_reasons = {}

    for discharge in discharge_data:
        uid = discharge.get('UID')
        if not uid or uid in discharge_processed_uids:
            continue
        discharge_processed_uids.add(uid)

        critical_reasons_field = discharge.get('criticalReasons', '')
        # Only process entries that have actual critical reasons (ignore empty/null values)
        if isinstance(critical_reasons_field, str) and critical_reasons_field.strip():
            critical_reason = critical_reasons_field.strip()

            if critical_reason not in discharge_critical_reasons:
                discharge_critical_reasons[critical_reason] = {
                    'count': 0,
                    'discharges': []
                }

            discharge_critical_reasons[critical_reason]['count'] += 1
            discharge_critical_reasons[critical_reason]['discharges'].append({
                'UID': uid,
                'hospitalName': discharge.get('hospitalName', 'Unknown'),
                'criticalReason': critical_reason,
                'dischargeType': discharge.get('dischargeType', 'Unknown'),
                'dischargeStatus': discharge.get('dischargeStatus', 'Unknown'),
                'source': 'discharges collection'
            })

    return {
        'discharge_critical_reasons': discharge_critical_reasons,
        'total_discharges_with_reasons': sum(data['count'] for data in discharge_critical_reasons.values()),
        'total_discharges': len(discharge_processed_uids)
    }

def calculate_kmc_verification_monitoring(baby_data):
    """Calculate KMC verification monitoring with total numbers"""
    processed_uids = set()

    verification_stats = {
        'correct': 0,
        'incorrect': 0,
        'unable_to_verify': 0,
        'not_verified': 0,
        'total_observations': 0
    }

    detailed_data = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)

        observation_days = baby.get('observationDay', [])

        for obs_day in observation_days:
            verification_stats['total_observations'] += 1

            # Check KMC verification fields with true/false logic
            filled_correctly = obs_day.get('filledCorrectly')
            kmc_filled_correctly = obs_day.get('kmcfilledcorrectly')
            mne_comment = obs_day.get('mnecomment', '')

            status = 'not_verified'  # Default

            # Priority logic:
            # 1. If mnecomment exists, it's incorrect
            # 2. Check boolean values for verification status
            if mne_comment and mne_comment.strip():
                status = 'incorrect'
            elif filled_correctly is True:
                status = 'correct'
            elif filled_correctly is False:
                status = 'incorrect'
            elif kmc_filled_correctly is True:
                status = 'correct'
            elif kmc_filled_correctly is False:
                status = 'incorrect'
            # If string-based values still exist, handle them as fallback
            elif isinstance(kmc_filled_correctly, str) and kmc_filled_correctly:
                kmc_lower = kmc_filled_correctly.lower()
                if kmc_lower == 'correct' or kmc_lower == 'true':
                    status = 'correct'
                elif kmc_lower == 'incorrect' or kmc_lower == 'false':
                    status = 'incorrect'
                elif 'unable' in kmc_lower:
                    status = 'unable_to_verify'

            verification_stats[status] += 1

            detailed_data.append({
                'UID': uid,
                'hospitalName': baby.get('hospitalName', 'Unknown'),
                'observationDate': obs_day.get('date', 'Unknown'),
                'ageDay': obs_day.get('ageDay', 'Unknown'),
                'status': status,
                'filledCorrectly': filled_correctly,
                'kmcfilledcorrectly': kmc_filled_correctly,
                'mnecomment': mne_comment,
                'observation_data': {k: v for k, v in obs_day.items() if k not in ['filledCorrectly', 'kmcfilledcorrectly', 'mnecomment', 'date', 'ageDay']}
            })

    return {
        'verification_stats': verification_stats,
        'detailed_data': detailed_data,
        'total_babies': len(processed_uids)
    }

def calculate_observations_verification_monitoring(baby_data):
    """Calculate observations verification monitoring with total numbers"""
    processed_uids = set()

    verification_stats = {
        'correct_or_not_checked': 0,
        'incorrect': 0,
        'total_observations': 0
    }

    detailed_data = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)

        observation_days = baby.get('observationDay', [])

        for obs_day in observation_days:
            verification_stats['total_observations'] += 1

            # Check observations verification fields with true/false logic
            filled_incorrectly = obs_day.get('filledincorrectly')
            mne_comment = obs_day.get('mnecomment', '')

            status = 'correct_or_not_checked'  # Default

            # Logic: if comment there, then it wasn't correct
            # Use boolean true/false values for filledincorrectly
            if mne_comment and mne_comment.strip():
                status = 'incorrect'
            elif filled_incorrectly is True:
                status = 'incorrect'

            verification_stats[status] += 1

            detailed_data.append({
                'UID': uid,
                'hospitalName': baby.get('hospitalName', 'Unknown'),
                'observationDate': obs_day.get('date', 'Unknown'),
                'ageDay': obs_day.get('ageDay', 'Unknown'),
                'status': status,
                'filledincorrectly': filled_incorrectly,
                'mnecomment': mne_comment,
                'observation_data': {k: v for k, v in obs_day.items() if k not in ['filledincorrectly', 'mnecomment', 'date', 'ageDay']}
            })

    return {
        'verification_stats': verification_stats,
        'detailed_data': detailed_data,
        'total_babies': len(processed_uids)
    }



@st.cache_data(show_spinner=False, ttl=900)
@st.cache_data(show_spinner=False, ttl=900)
def calculate_discharged_babies_without_kmc(_baby_data, _discharge_data):
    """Calculate hospital-wise analysis of discharged babies without any KMC observations"""

    # Create set of selected baby UIDs for filtering (same pattern as calculate_discharge_outcomes)
    selected_baby_uids = {baby.get('UID') for baby in _baby_data if baby.get('UID')}

    # Get all discharged babies - from both discharges collection and babyBackUp
    discharged_babies = {}
    processed_uids = set()

    # Process discharges collection
    for discharge in _discharge_data:
        uid = discharge.get('UID')
        # Filter by baby UIDs (same pattern as other functions)
        if not uid or uid in processed_uids or uid not in selected_baby_uids:
            continue

        hospital = discharge.get('hospitalName', 'Unknown')

        # Skip training hospitals
        hospital_name_lower = hospital.lower()
        if any(term in hospital_name_lower for term in ['test', 'training', 'demo']):
            continue

        processed_uids.add(uid)

        if hospital not in discharged_babies:
            discharged_babies[hospital] = {
                'total_discharged': 0,
                'without_kmc': 0,
                'babies_without_kmc': []
            }

        discharged_babies[hospital]['total_discharged'] += 1

        # Find this baby in baby_data to check KMC status
        baby_kmc_found = False
        for baby in _baby_data:
            if baby.get('UID') == uid:
                # Check if baby has any KMC observations using timeInKMC arrays
                # If there is even 1 timeInKMC session in any observationDay, baby is considered with KMC
                observation_days = baby.get('observationDay', [])
                has_kmc = False

                for obs_day in observation_days:
                    # Check if this observation day has any timeInKMC sessions
                    time_in_kmc_array = obs_day.get('timeInKMC', [])
                    if isinstance(time_in_kmc_array, list) and len(time_in_kmc_array) > 0:
                        # Further check if any session has actual data (not just empty dict)
                        for session in time_in_kmc_array:
                            if isinstance(session, dict) and session:  # Non-empty session
                                has_kmc = True
                                break

                    if has_kmc:
                        break

                if not has_kmc:
                    discharged_babies[hospital]['without_kmc'] += 1
                    discharged_babies[hospital]['babies_without_kmc'].append({
                        'UID': uid,
                        'motherName': baby.get('motherName', 'Unknown'),
                        'dischargeStatus': discharge.get('dischargeStatus', 'Unknown'),
                        'dischargeDate': discharge.get('dischargeDate')
                    })

                baby_kmc_found = True
                break

        # If baby not found in baby_data, assume no KMC
        if not baby_kmc_found:
            discharged_babies[hospital]['without_kmc'] += 1
            discharged_babies[hospital]['babies_without_kmc'].append({
                'UID': uid,
                'motherName': 'Unknown',
                'dischargeStatus': discharge.get('dischargeStatus', 'Unknown'),
                'dischargeDate': discharge.get('dischargeDate')
            })




    # Calculate percentages and totals
    for hospital_data in discharged_babies.values():
        total = hospital_data['total_discharged']
        without_kmc = hospital_data['without_kmc']
        hospital_data['percentage_without_kmc'] = (without_kmc / total * 100) if total > 0 else 0

    total_discharged = sum(data['total_discharged'] for data in discharged_babies.values())
    total_without_kmc = sum(data['without_kmc'] for data in discharged_babies.values())

    return {
        'hospital_data': discharged_babies,
        'total_discharged': total_discharged,
        'total_without_kmc': total_without_kmc,
        'overall_percentage': (total_without_kmc / total_discharged * 100) if total_discharged > 0 else 0
    }

@st.cache_data(show_spinner=False, ttl=900)
def calculate_individual_critical_reasons(_baby_data, _discharge_data):
    """Calculate individual critical reasons from discharges collection - parse array-like strings"""
    import ast
    import re

    # Create set of selected baby UIDs for filtering (same pattern as calculate_discharge_outcomes)
    selected_baby_uids = {baby.get('UID') for baby in _baby_data if baby.get('UID')}

    # Track individual critical reasons
    individual_reasons = {}
    total_babies_with_reasons = 0
    processed_uids = set()

    for discharge in _discharge_data:
        uid = discharge.get('UID')
        # Filter by baby UIDs (same pattern as other functions)
        if not uid or uid not in selected_baby_uids or uid in processed_uids:
            continue

        critical_reasons_field = discharge.get('criticalReasons', '')

        # Only process entries that have actual critical reasons data
        if not critical_reasons_field or not str(critical_reasons_field).strip():
            continue

        processed_uids.add(uid)
        total_babies_with_reasons += 1

        try:
            # Parse the string representation of array (e.g., "['GA', 'weightLoss>2%']")
            critical_reasons_str = str(critical_reasons_field).strip()

            # Handle different formats
            if critical_reasons_str.startswith('[') and critical_reasons_str.endswith(']'):
                # Try to parse as Python list literal
                try:
                    reasons_list = ast.literal_eval(critical_reasons_str)
                except:
                    # Fallback: extract items using regex
                    reasons_list = re.findall(r"'([^']*)'", critical_reasons_str)
            else:
                # Single reason, not in array format
                reasons_list = [critical_reasons_str]

            # Count each individual reason
            for reason in reasons_list:
                reason = str(reason).strip()
                if reason:
                    if reason not in individual_reasons:
                        individual_reasons[reason] = {
                            'count': 0,
                            'babies': []
                        }

                    individual_reasons[reason]['count'] += 1
                    individual_reasons[reason]['babies'].append({
                        'UID': uid,
                        'hospital': discharge.get('hospitalName', 'Unknown'),
                        'dischargeStatus': discharge.get('dischargeStatus', 'Unknown'),
                        'full_reasons': critical_reasons_str
                    })

        except Exception as e:
            # If parsing fails, treat as single reason
            reason = str(critical_reasons_field).strip()
            if reason:
                if reason not in individual_reasons:
                    individual_reasons[reason] = {
                        'count': 0,
                        'babies': []
                    }

                individual_reasons[reason]['count'] += 1
                individual_reasons[reason]['babies'].append({
                    'UID': uid,
                    'hospital': discharge.get('hospitalName', 'Unknown'),
                    'dischargeStatus': discharge.get('dischargeStatus', 'Unknown'),
                    'full_reasons': critical_reasons_field
                })

    return {
        'individual_reasons': individual_reasons,
        'total_babies_with_reasons': total_babies_with_reasons,
        'total_unique_reasons': len(individual_reasons)
    }

@st.cache_data(show_spinner=False, ttl=900)
@st.cache_data(show_spinner=False, ttl=900)
def calculate_individual_baby_metrics(baby_data):
    """Calculate comprehensive metrics for each individual baby"""
    processed_uids = set()
    baby_metrics = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)

        # Basic baby info
        mother_name = baby.get('motherName', 'Unknown')
        hospital = baby.get('hospitalName', 'Unknown')
        location = baby.get('currentLocationOfTheBaby', 'Unknown')
        dead_baby = baby.get('deadBaby', False)
        danger_signs = baby.get('dangerSigns', 'Not specified')

        # Calculate KMC metrics
        total_kmc_minutes = 0
        kmc_days_count = 0
        
        # New structure: age_days
        age_days = baby.get('age_days', [])
        for day in age_days:
            kmc_time = day.get('totalKMCToday', 0)
            if kmc_time > 0:
                total_kmc_minutes += kmc_time
                kmc_days_count += 1
        
        # Legacy fallback
        if not age_days and 'observationDay' in baby:
            for obs_day in baby.get('observationDay', []):
                kmc_time = obs_day.get('totalKMCtimeDay', 0)
                if kmc_time > 0:
                    total_kmc_minutes += kmc_time
                    kmc_days_count += 1

        total_kmc_hours = total_kmc_minutes / 60 if total_kmc_minutes > 0 else 0
        avg_kmc_per_day = total_kmc_hours / kmc_days_count if kmc_days_count > 0 else 0

        # Calculate follow-up KMC averages for specific follow-up numbers
        followup_kmc = {2: [], 7: [], 14: [], 28: []}

        followup_array = baby.get('followUp', [])
        for followup_entry in followup_array:
            followup_number = followup_entry.get('followUpNumber')
            if followup_number in followup_kmc:
                kmc_time = followup_entry.get('totalKMCTime')
                if kmc_time is not None:
                    try:
                        kmc_hours = float(kmc_time) / 60 if float(kmc_time) > 0 else 0
                        followup_kmc[followup_number].append(kmc_hours)
                    except (ValueError, TypeError):
                        pass

        # Calculate averages for each follow-up
        followup_averages = {}
        for followup_num, times in followup_kmc.items():
            if times:
                followup_averages[f'Follow-up {followup_num}'] = f"{sum(times)/len(times):.1f}h"
            else:
                followup_averages[f'Follow-up {followup_num}'] = "No data"

        baby_metrics.append({
            'UID': uid,
            'Mother Name': mother_name,
            'Hospital': hospital,
            'Location': location,
            'Total KMC Hours': f"{total_kmc_hours:.1f}h",
            'Avg KMC Hours/Day': f"{avg_kmc_per_day:.1f}h",
            'KMC Days Count': kmc_days_count,
            'Follow-up 2': followup_averages['Follow-up 2'],
            'Follow-up 7': followup_averages['Follow-up 7'],
            'Follow-up 14': followup_averages['Follow-up 14'],
            'Follow-up 28': followup_averages['Follow-up 28'],
            'Dead Baby': 'Yes' if dead_baby else 'No',
            'Danger Signs': danger_signs,
            'Birth Date': convert_unix_to_datetime(baby.get('dateOfBirth')),
            'Source': baby.get('source', 'Unknown')
        })

    return baby_metrics

def calculate_skin_contact_metrics(baby_data):
    """Calculate average numberSkinContact from all followups EXCEPT followUp28 in baby/babybackup collections"""
    processed_uids = set()
    skin_contact_data = []
    high_skin_contact_alerts = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)

        # Look for all followups EXCEPT followUp28 in the followUp array
        followup_array = baby.get('followUp', [])
        for followup_entry in followup_array:
            followup_number = followup_entry.get('followUpNumber')

            # Skip followUp28 as requested
            if followup_number == 28:
                continue

            number_skin_contact = followup_entry.get('numberSkinContact')
            if number_skin_contact is not None:
                try:
                    skin_contact_value = float(number_skin_contact)

                    skin_contact_data.append({
                        'UID': uid,
                        'hospital': baby.get('hospitalName', 'Unknown'),
                        'numberSkinContact': skin_contact_value,
                        'followUpNumber': followup_number
                    })

                    # Alert for skin-to-skin contact > 10
                    if skin_contact_value > 10:
                        high_skin_contact_alerts.append({
                            'UID': uid,
                            'hospital': baby.get('hospitalName', 'Unknown'),
                            'numberSkinContact': skin_contact_value,
                            'followUpNumber': followup_number
                        })

                except (ValueError, TypeError):
                    pass  # Skip invalid values
    
    if not skin_contact_data:
        return {
            'total_babies_with_data': 0,
            'average_skin_contact': 0,
            'min_skin_contact': 0,
            'max_skin_contact': 0,
            'skin_contact_data': [],
            'high_skin_contact_alerts': []
        }

    values = [item['numberSkinContact'] for item in skin_contact_data]

    return {
        'total_babies_with_data': len(skin_contact_data),
        'average_skin_contact': sum(values) / len(values),
        'min_skin_contact': min(values),
        'max_skin_contact': max(values),
        'skin_contact_data': skin_contact_data,
        'high_skin_contact_alerts': high_skin_contact_alerts
    }

def analyze_kmc_filled_correctly(baby_data):
    """Analyze KMCfilledcorrectlystring categorization"""
    processed_uids = set()
    kmc_filled_data = {
        'correct': [],
        'incorrect': [],
        'missing': []
    }
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        # Check KMCfilledcorrectlystring (Using Observations)
        observations = baby.get('observations', [])
        
        # If new structure exists
        if observations:
            for obs in observations:
                kmc_filled_string = obs.get('KMCfilledcorrectlystring', '').lower()
                me_comment = obs.get('verificationNotes', 'No comment')
                
                # We need to link to age_days to get KMC hours for context if needed
                # For now just checking the string as strictly requested
                
                entry_data = {
                    'UID': uid,
                    'hospital': baby.get('hospitalName', 'Unknown'),
                    'ageDay': obs.get('ageDay', 'Unknown'),
                    'KMChours': 0, # Difficult to link easily without more logic, but user request focused on structure
                    'MEComment': me_comment,
                    'KMCfilledcorrectlystring': obs.get('KMCfilledcorrectlystring', 'Missing'),
                    'baby_data': baby
                }
                
                if not kmc_filled_string:
                    kmc_filled_data['missing'].append(entry_data)
                elif 'correct' in kmc_filled_string or 'true' in kmc_filled_string:
                    kmc_filled_data['correct'].append(entry_data)
                elif 'incorrect' in kmc_filled_string or 'false' in kmc_filled_string:
                    kmc_filled_data['incorrect'].append(entry_data)
                else:
                    kmc_filled_data['incorrect'].append(entry_data) 

        # Legacy fallback
        elif 'observationDay' in baby:
            for obs_day in baby.get('observationDay', []):
                kmc_filled_string = obs_day.get('KMCfilledcorrectlystring', '').lower()
                kmc_hours = obs_day.get('totalKMCtimeDay', 0) / 60 if obs_day.get('totalKMCtimeDay') else 0
                age_day = obs_day.get('ageDay', 'Unknown')
                me_comment = obs_day.get('MEComment', 'No comment')
                
                entry_data = {
                    'UID': uid,
                    'hospital': baby.get('hospitalName', 'Unknown'),
                    'ageDay': age_day,
                    'KMChours': round(kmc_hours, 1),
                    'MEComment': me_comment,
                    'KMCfilledcorrectlystring': obs_day.get('KMCfilledcorrectlystring', 'Missing'),
                    'baby_data': baby
                }
                
                if not kmc_filled_string:
                    kmc_filled_data['missing'].append(entry_data)
                elif 'correct' in kmc_filled_string or 'true' in kmc_filled_string:
                    kmc_filled_data['correct'].append(entry_data)
                elif 'incorrect' in kmc_filled_string or 'false' in kmc_filled_string:
                    kmc_filled_data['incorrect'].append(entry_data)
                else:
                    kmc_filled_data['incorrect'].append(entry_data)  # Default unclear to incorrect
    
    return kmc_filled_data

def analyze_observation_filled_correctly(baby_data):
    """Analyze observation day filledcorrectly field"""
    processed_uids = set()
    obs_filled_data = {
        'correct': [],
        'incorrect': [],
        'missing': []
    }
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        # Check filledcorrectly in Observations
        observations = baby.get('observations', [])
        
        if observations:
            for obs in observations:
                filled_correctly = None
                status = obs.get('verificationStatus', '').lower()
                if status == 'correct': filled_correctly = True
                elif status == 'incorrect': filled_correctly = False
                
                me_comment = obs.get('verificationNotes', 'No comment')
                
                entry_data = {
                    'UID': uid,
                    'hospital': baby.get('hospitalName', 'Unknown'),
                    'ageDay': obs.get('ageDay', 'Unknown'),
                    'KMChours': 0,
                    'MEComment': me_comment,
                    'filledcorrectly': filled_correctly,
                    'baby_data': baby
                }
                
                if filled_correctly is None:
                    obs_filled_data['missing'].append(entry_data)
                elif filled_correctly == True:
                    obs_filled_data['correct'].append(entry_data)
                elif filled_correctly == False:
                    obs_filled_data['incorrect'].append(entry_data)
                else:
                    obs_filled_data['missing'].append(entry_data)

        # Legacy fallback
        elif 'observationDay' in baby:
            for obs_day in baby.get('observationDay', []):
                filled_correctly = obs_day.get('filledcorrectly')
                kmc_hours = obs_day.get('totalKMCtimeDay', 0) / 60 if obs_day.get('totalKMCtimeDay') else 0
                age_day = obs_day.get('ageDay', 'Unknown')
                me_comment = obs_day.get('MEComment', 'No comment')
                
                entry_data = {
                    'UID': uid,
                    'hospital': baby.get('hospitalName', 'Unknown'),
                    'ageDay': age_day,
                    'KMChours': round(kmc_hours, 1),
                    'MEComment': me_comment,
                    'filledcorrectly': filled_correctly,
                    'baby_data': baby
                }
                
                if filled_correctly is None:
                    obs_filled_data['missing'].append(entry_data)
                elif filled_correctly == True:
                    obs_filled_data['correct'].append(entry_data)
                elif filled_correctly == False:
                    obs_filled_data['incorrect'].append(entry_data)
                else:
                    obs_filled_data['missing'].append(entry_data)
    
    return obs_filled_data

def find_high_kmc_followups(baby_data):
    """Find follow-ups with KMC hours >12 per day including nurse name"""
    high_kmc_data = []
    processed_uids = set()
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        # Check follow-up entries
        followup_array = baby.get('followUp', [])
        for followup_entry in followup_array:
            # Check if there are KMC hours data
            kmc_hours = followup_entry.get('kmcHours', 0)
            if kmc_hours > 12:  # More than 12 hours per day
                high_kmc_data.append({
                    'UID': uid,
                    'hospital': baby.get('hospitalName', 'Unknown'),
                    'followUpNumber': followup_entry.get('followUpNumber', 'Unknown'),
                    'KMChours': kmc_hours,
                    'nurseName': followup_entry.get('nurseName', baby.get('nurseName', 'Not specified')),
                    'followUpDate': followup_entry.get('date', 'Unknown'),
                    'dataset': baby.get('source', 'baby'),
                    'baby_data': baby
                })
    
    return high_kmc_data

def analyze_kmc_filled_comparison(baby_data):
    """Compare kmcFilledCorrectlyString = 'correct' vs KMCfilledCorrectly = false"""
    comparison_data = {
        'string_correct': [],
        'boolean_false': [],
        'both_mismatch': []
    }
    processed_uids = set()
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        # Check observation days
        for obs_day in baby.get('observationDay', []):
            kmc_filled_string = obs_day.get('KMCfilledcorrectlystring', '').lower()
            kmc_filled_correctly = obs_day.get('KMCfilledCorrectly')  # Note the capital C
            kmc_hours = obs_day.get('totalKMCtimeDay', 0) / 60 if obs_day.get('totalKMCtimeDay') else 0
            age_day = obs_day.get('ageDay', 'Unknown')
            me_comment = obs_day.get('MEComment', 'No comment')
            
            entry_data = {
                'UID': uid,
                'hospital': baby.get('hospitalName', 'Unknown'),
                'ageDay': age_day,
                'KMChours': round(kmc_hours, 1),
                'MEComment': me_comment,
                'KMCfilledcorrectlystring': obs_day.get('KMCfilledcorrectlystring', 'Missing'),
                'KMCfilledCorrectly': kmc_filled_correctly,
                'baby_data': baby
            }
            
            # Check for kmcFilledCorrectlyString = "correct"
            if 'correct' in kmc_filled_string:
                comparison_data['string_correct'].append(entry_data)
            
            # Check for KMCfilledCorrectly = false
            if kmc_filled_correctly == False:
                comparison_data['boolean_false'].append(entry_data)
                
            # Check for mismatch (string says correct but boolean is false)
            if 'correct' in kmc_filled_string and kmc_filled_correctly == False:
                comparison_data['both_mismatch'].append(entry_data)
    
    return comparison_data

# ===== DATA EXPORT FUNCTIONS =====

def _prepare_sandbox_data(baby_data):
    """Reconstruct flat lists for Sandbox Metrics tab"""
    kmc_sessions = []
    # observations = [] # Not used directly in sandbox tab logic yet, kept if needed
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid: continue
        
        # Check observationDay for KMC sessions
        for day in baby.get('observationDay', []):
            # KMC Sessions
            for sess in day.get('timeInKMC', []):
                # Ensure we have start time
                if not sess.get('timeStartKMC'): continue
                
                new_sess = {
                    'idBaby': uid,
                    'UID': uid,
                    'kmcStart': sess.get('timeStartKMC'),
                    'kmcEnd': sess.get('timeEndKMC'),
                    'kmcDuration': sess.get('duration'), # minutes
                    'kmcProvider': sess.get('provider')
                }
                kmc_sessions.append(new_sess)
                
    return kmc_sessions

# ===== END DATA EXPORT FUNCTIONS =====


# Custom CSS (load before authentication to style landing page)
st.markdown(f"""
<style>
    .main-header {{
        background: linear-gradient(90deg, {PROJECT_COLORS['primary']} 0%, {PROJECT_COLORS['secondary']} 100%);
        padding: 1rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        text-align: center;
    }}
    .metric-container {{
        background: {PROJECT_COLORS['light']};
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid {PROJECT_COLORS['primary']};
        margin: 1rem 0;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: {PROJECT_COLORS['light']};
        color: {PROJECT_COLORS['dark']};
        border-radius: 10px 10px 0 0;
        margin-right: 5px;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background: {PROJECT_COLORS['secondary']};
        color: white;
    }}
</style>
""", unsafe_allow_html=True)

def main():

    # Header
    st.markdown(f"""
    <div class="main-header">
        <h1>👶 {HEADER_TITLE}</h1>
        <p>Real-time monitoring of Kangaroo Mother Care program across hospitals</p>
    </div>
    """, unsafe_allow_html=True)



    # Initialize session state for first load
    if 'first_load' not in st.session_state:
        st.session_state.first_load = True

    # Auto-run on first load for initial data load
    initial_run = st.session_state.first_load
    if initial_run:
        st.session_state.first_load = False

    # Filters in a clearer hierarchy
    with st.sidebar.expander("🔍 Filters & Analysis", expanded=True):
        st.markdown("#### 🌐 Server-Side Filters")
        st.caption("These filters fetch data from Firebase")
        
        # Date Selection
        date_preset = st.selectbox(
            "📅 Time Period",
            ["Last 7 days", "Last 30 days", "Last 90 days", "All Time", "Custom Range"],
            index=0,
            key="filter_date_preset"
        )

        today = datetime.now().date()
        preset_start_date = None
        preset_end_date = None

        # Calculate preset dates
        if date_preset == "Last 7 days":
            preset_start_date = today - timedelta(days=7)
            preset_end_date = today
        elif date_preset == "Last 30 days":
            preset_start_date = today - timedelta(days=30)
            preset_end_date = today
        elif date_preset == "Last 90 days":
            preset_start_date = today - timedelta(days=90)
            preset_end_date = today
        elif date_preset == "All Time":
            preset_start_date = datetime(2023, 1, 1).date()
            preset_end_date = today
        
        # If a preset is selected, update the session state to reflect it
        if date_preset != "Custom Range":
            st.session_state['custom_start_date'] = preset_start_date
            st.session_state['custom_end_date'] = preset_end_date
        
        # Determine values for widgets to avoid warnings
        # We must pass the same value to the widget as what is in session state
        val_start = st.session_state.get('custom_start_date', today - timedelta(days=30))
        val_end = st.session_state.get('custom_end_date', today)

        # Render the date inputs (Always visible, disabled if using a preset)
        is_disabled = (date_preset != "Custom Range")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From",
                value=val_start,
                max_value=today,
                disabled=is_disabled,
                key="custom_start_date")
        with col2:
            end_date = st.date_input("To",
                value=val_end,
                min_value=start_date,
                max_value=today,
                disabled=is_disabled,
                key="custom_end_date")

        # UID Search
        search_uid = st.text_input("🔎 Search by UID (Exact Match)", placeholder="Enter exact UID...", key="filter_uid")

        # Hospital Filter (Server-Side)
        # Initialize hospital list in session state if not present
        if 'hospital_list' not in st.session_state:
            st.session_state.hospital_list = []
        
        # All hospitals available
        available_hospitals = st.session_state.hospital_list
        default_hospitals = []  # Empty means "All Hospitals"
        placeholder_text = "All Hospitals"

        selected_hospitals = st.multiselect(
            "🏥 Hospitals", 
            available_hospitals, 
            default=default_hospitals,
            placeholder=placeholder_text,
            key="filter_hospital_server"
        )

        st.markdown("---")
        run_analysis = st.button("🔄 Load Data", type="primary", use_container_width=True)
        st.caption("⚡ Fetches data from Firebase")
    
    # Get selected_hospitals from session state if form was submitted, otherwise use last value or empty list
    if 'filter_hospital_server' in st.session_state:
        selected_hospitals = st.session_state.filter_hospital_server
    else:
        selected_hospitals = []
    

    
    # Trigger run on initial load
    if initial_run:
        run_analysis = True

    # Persist dates in session state
    if 'last_start_date' not in st.session_state:
        st.session_state.last_start_date = start_date
        st.session_state.last_end_date = end_date
    
    if 'last_uid' not in st.session_state:
        st.session_state.last_uid = search_uid

    if 'last_hospitals' not in st.session_state:
        st.session_state.last_hospitals = selected_hospitals
    
    if run_analysis:
        # Check if dates, UID, or Hospital have changed to clear cache
        # Compare lists for hospitals
        hospitals_changed = False
        if st.session_state.get('last_hospitals') != selected_hospitals:
            hospitals_changed = True

        if (st.session_state.last_start_date != start_date or 
            st.session_state.last_end_date != end_date or
            st.session_state.get('last_uid') != search_uid or
            hospitals_changed):
            st.cache_data.clear()
            
        st.session_state.last_start_date = start_date
        st.session_state.last_end_date = end_date
        st.session_state.last_uid = search_uid
        st.session_state.last_hospitals = selected_hospitals

    # Load data using the stored dates, UID, and Hospitals
    effective_hospitals = st.session_state.last_hospitals if st.session_state.last_hospitals else None

    baby_data, discharge_data, followup_data = load_firebase_data(
        st.session_state.last_start_date, 
        st.session_state.last_end_date,
        st.session_state.last_uid if st.session_state.last_uid else None,
        effective_hospitals
    )

    # Update Hospital List from loaded data (Bootstrap approach)
    # Only update if we have data and the list is just 'All' (or to keep it fresh)
    if baby_data:
        current_hospitals = sorted(list(set(baby.get('hospitalName') for baby in baby_data if baby.get('hospitalName'))))
        # Merge with existing list to avoid losing options if we filter down
        # Actually, we want to keep ALL known hospitals available.
        # If we filter by Hospital A, the data will only show Hospital A.
        # So we should ONLY update the list if we are in "All" mode or if the list is empty.
        # Better strategy: Add any new hospitals found to the global list.
        
        new_hospitals = set(st.session_state.hospital_list)
        new_hospitals.update(current_hospitals)
        
        final_list = sorted(list(new_hospitals))
        
        if final_list != st.session_state.hospital_list:
            st.session_state.hospital_list = final_list
            # Rerun to update the selectbox options visually immediately
            st.rerun()

    if not baby_data:
        st.error("⚠️ No data loaded from Firebase.")
        st.info("Please select a date range and click 'Apply Filters'.")
        st.markdown("---")
        st.header("KMC Dashboard - Waiting for Data")
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "📈 Clinical KPIs", "📋 Mortality Analysis", "⏰ Daily KMC Analysis", "👩‍⚕️ Nurses Analysis"])
        with tab1: st.info("No data available")
        return

    # App-side filters section removed as per user request
    # We now use the loaded baby_data directly as filtered_data
    import time
    proc_start = time.time()
    filtered_data = baby_data
    
    # UID filtering is now server-side, but we keep this as a fallback or for additional filtering if needed
    if search_uid and not st.session_state.last_uid:
        # Only apply client-side if server-side wasn't used
        filtered_data = [baby for baby in filtered_data if search_uid.lower() in baby.get('UID', '').lower()]
        
    st.session_state['last_processing_duration'] = time.time() - proc_start

    # ===== DATA DOWNLOAD SECTION =====
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 📥 Data Download")
    
    # Generate CSV when button is clicked
    csv_string, filename, stats = generate_csv_download(
        filtered_data, 
        discharge_data, 
        st.session_state.get('last_hospitals', []),
        st.session_state.get('last_start_date'),
        st.session_state.get('last_end_date')
    )
    
    if csv_string:
        st.sidebar.download_button(
            label="📊 Download Baby Data (CSV)",
            data=csv_string,
            file_name=filename,
            mime="text/csv",
            use_container_width=True
        )
        
        # Show summary statistics in expander
        with st.sidebar.expander("📈 Download Summary", expanded=False):
            st.markdown(f"""
**Total Babies:** {stats['total']:,}

**KMC Stability:**
- Stable: {stats['stable']:,}
- Unstable: {stats['unstable']:,}

**Mortality:**
- Alive: {stats['alive']:,}
- Dead: {stats['dead']:,}

**Birth Place:**
- Inborn: {stats['inborn']:,}
- Outborn: {stats['outborn']:,}

**Follow-ups:**
- 28-day F/U available: {stats['followup_28_available']:,}
            """)
    else:
        st.sidebar.info("No data available to download")
    # ===== END DATA DOWNLOAD SECTION =====

    # Data Verification section (Sidebar)
    if 'db_total_count' not in st.session_state:
        st.session_state.db_total_count = get_db_counts()
    
    if st.session_state.db_total_count:
        st.sidebar.markdown("---")
        st.sidebar.markdown("#### 🔢 Data Verification")
        st.sidebar.info(f"""
        **Total in DB:** {st.session_state.db_total_count:,}  
        **Loaded:** {len(baby_data):,}
        """)

    # RAM monitoring for cloud debugging
    st.sidebar.markdown("---")
    
    # Display System Health Panel at the bottom
    display_system_health()
    
    st.sidebar.caption("💡 For Streamlit Cloud debugging")

    # ===== CONNECTION STATUS SECTION (Bottom of Sidebar) =====
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🔌 Connection Status")

    if USE_FAKE_DATA:
        st.sidebar.warning("⚠️ Using Fake Data Mode")
    else:
        # Check if using secrets or local file (logic mirrored from initialize_firebase)
        try:
            if "gcp_service_account" in st.secrets:
                st.sidebar.success("✅ Using Streamlit secrets for Firebase connection")
            else:
                 st.sidebar.info("ℹ️ Using local/other configuration")
        except FileNotFoundError:
             st.sidebar.info("ℹ️ Using local configuration")
        except Exception:
             pass

        # If we have data, we are connected
        if baby_data or discharge_data:
            st.sidebar.success("🔥 Firebase connection verified successfully!")
            
            # Show query info
            if 'last_start_date' in st.session_state and 'last_end_date' in st.session_state:
                s_date = st.session_state.last_start_date
                e_date = st.session_state.last_end_date
                st.sidebar.info(f"🔍 Querying Firebase for birthDate between {s_date} and {e_date}")

    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Overview", "📈 Clinical KPIs", "📋 Mortality Analysis", "⏰ Daily KMC Analysis", "👩‍⚕️ Nurses Analysis", "🏗️ Sandbox Metrics"])
    
    with tab1:
        render_overview_tab(baby_data, filtered_data)
    
    with tab2:
        render_clinical_kpis_tab(filtered_data, discharge_data, followup_data, start_date, end_date)

    with tab3:
        render_mortality_tab(baby_data, filtered_data, discharge_data)

    with tab4:
        render_daily_kmc_tab(filtered_data, discharge_data)

    with tab5:
        # Use effective_hospitals for the nurses tab filtering
        render_nurses_tab(filtered_data, discharge_data, start_date, end_date, effective_hospitals)

    with tab6:
        # Prepare data for Sandbox tab
        sandbox_kmc_sessions = _prepare_sandbox_data(filtered_data)
        render_sandbox_tab(filtered_data, discharge_data, followup_data, sandbox_kmc_sessions)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        st.error("🚨 **Critical Application Error - Running in Safe Mode**")
        st.error(f"Error: {str(e)}")

        # Always show a basic interface so the app doesn't completely crash
        st.header("KMC Dashboard - Safe Mode")
        st.write("💡 **The application encountered an unexpected error but is still running.**")
        st.write("🔄 Try refreshing the page or check your internet connection.")

        # Show basic empty interface
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Babies", "Data Unavailable")
            st.metric("Hospitals", "Data Unavailable")
        with col2:
            st.metric("Discharges", "Data Unavailable")
            st.metric("Follow-ups", "Data Unavailable")

        # Debug information in expander
        with st.expander("🔧 Technical Details (for developers)"):
            st.text("Full error traceback:")
            st.code(traceback.format_exc())
            st.write("**Troubleshooting Steps:**")
            st.write("1. Check internet connection")
            st.write("2. Verify Firebase credentials")
            st.write("3. Try refreshing the browser")
            st.write("4. Contact support if issue persists")

        # Keep the app alive with a retry button
        if st.button("🔄 Retry Application"):
            st.rerun()

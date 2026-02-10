"""
Dashboard metrics - KPI calculations and analysis functions.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dashboard_utils import (
    convert_unix_to_datetime, 
    check_kmc_stability,
    categorize_discharge,
    get_prioritized_discharge_weight,
    get_prioritized_discharge_temperature,
    get_prioritized_discharge_rr,
    get_prioritized_feed_mode,
    get_prioritized_baby_health,
    get_prioritized_critical_reasons,
    get_prioritized_discharge_reason,
    get_hierarchical_discharge_date
)


@st.cache_data(show_spinner=False, ttl=900, max_entries=20)
def calculate_registration_timeliness(baby_data):
    """Calculate registration timeliness KPIs"""
    inborn_babies = [baby for baby in baby_data 
                    if baby.get('placeOfDelivery') in ['यह अस्पताल', 'this hospital']]
    
    within_24h = 0
    within_12h = 0
    
    for baby in inborn_babies:
        birth_time = convert_unix_to_datetime(baby.get('dateOfBirth'))
        reg_time = convert_unix_to_datetime(baby.get('registrationDate') or 
                                         baby.get('registrationDataType', {}).get('registrationDate'))
        
        if birth_time and reg_time:
            time_diff = (reg_time - birth_time).total_seconds() / 3600  # hours
            
            if 0 <= time_diff <= 24:
                within_24h += 1
                if time_diff <= 12:
                    within_12h += 1
    
    total_inborn = len(inborn_babies)
    
    return {
        'total_inborn': total_inborn,
        'within_24h_count': within_24h,
        'within_24h_percentage': (within_24h / total_inborn * 100) if total_inborn > 0 else 0,
        'within_12h_count': within_12h,
        'within_12h_percentage': (within_12h / total_inborn * 100) if total_inborn > 0 else 0
    }


@st.cache_data(show_spinner=False, ttl=900, max_entries=20)
def calculate_kmc_initiation_metrics(baby_data):
    """Calculate KMC initiation timing metrics categorized by inborn/outborn and location"""
    initiation_data = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid:
            continue

        birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
        if not birth_date:
            continue

        place_of_delivery = baby.get('placeOfDelivery', '')
        is_inborn = place_of_delivery in ['यह अस्पताल', 'this hospital']
        current_location = baby.get('currentLocationOfTheBaby', 'Unknown')


        # Find first KMC session using new kmc_sessions structure
        first_kmc_date = None
        first_kmc_hours = 0
        
        # Method 1: Check actual KMC sessions (Most accurate)
        kmc_sessions = baby.get('kmc_sessions', [])
        if kmc_sessions:
            for session in kmc_sessions:
                time_start = session.get('kmcStart')
                if time_start:
                    session_start = convert_unix_to_datetime(time_start)
                    if session_start:
                        if first_kmc_date is None or session_start < first_kmc_date:
                            first_kmc_date = session_start
                            # Use duration from this specific session if it's the first
                            first_kmc_hours = (session.get('kmcDuration', 0) / 60)
        
        # Method 2: Fallback to age_days if no sessions (Historic data)
        # Also need to get total hours for the first day
        if not first_kmc_date:
            age_days = baby.get('age_days', [])
            sorted_days = sorted(age_days, key=lambda x: x.get('ageDayNumber', 999))
            
            for day in sorted_days:
                if day.get('totalKMCToday', 0) > 0:
                    day_date = day.get('ageDayDate') # Timestamp
                    if day_date:
                        first_kmc_date = convert_unix_to_datetime(day_date)
                        first_kmc_hours = day.get('totalKMCToday', 0) / 60
                        break

        # Legacy Support: Check observationDay (for babyBackUp)
        if not first_kmc_date and 'observationDay' in baby:
             for obs_day in baby.get('observationDay', []):
                if obs_day.get('totalKMCtimeDay', 0) > 0:
                    age_day = obs_day.get('ageDay', 0)
                    kmc_date = birth_date + timedelta(days=age_day)
                    if first_kmc_date is None or kmc_date < first_kmc_date:
                        first_kmc_date = kmc_date
                        first_kmc_hours = obs_day.get('totalKMCtimeDay', 0) / 60
        
        if first_kmc_date:
            time_to_initiation = (first_kmc_date - birth_date).total_seconds() / 3600
            initiation_data.append({
                'UID': uid,
                'hospital': baby.get('hospitalName', 'Unknown'),
                'birth_date': birth_date,
                'first_kmc_date': first_kmc_date,
                'time_to_initiation_hours': time_to_initiation,
                'first_kmc_hours': first_kmc_hours,
                'is_inborn': is_inborn,
                'delivery_type': 'Inborn' if is_inborn else 'Outborn',
                'current_location': current_location
            })
    
    if not initiation_data:
        return {
            'total_babies_with_kmc': 0, 'avg_time_to_initiation_hours': 0,
            'within_24h_count': 0, 'within_24h_percentage': 0,
            'within_48h_count': 0, 'within_48h_percentage': 0,
            'initiation_data': [], 'inborn_stats': {}, 'outborn_stats': {},
            'inborn_location_stats': {}, 'inborn_location_hospital_stats': {}, 'hospital_stats': {}
        }

    total_babies = len(initiation_data)
    avg_time = sum(d['time_to_initiation_hours'] for d in initiation_data) / total_babies
    within_24h = len([d for d in initiation_data if d['time_to_initiation_hours'] <= 24])
    within_48h = len([d for d in initiation_data if d['time_to_initiation_hours'] <= 48])

    # Calculate stats by category
    inborn_data = [d for d in initiation_data if d['is_inborn']]
    outborn_data = [d for d in initiation_data if not d['is_inborn']]

    def calc_stats(data):
        if not data:
            return {}
        count = len(data)
        w24 = len([d for d in data if d['time_to_initiation_hours'] <= 24])
        w48 = len([d for d in data if d['time_to_initiation_hours'] <= 48])
        return {
            'count': count,
            'avg_time_hours': sum(d['time_to_initiation_hours'] for d in data) / count,
            'within_24h_count': w24, 'within_24h_percentage': w24 / count * 100,
            'within_48h_count': w48, 'within_48h_percentage': w48 / count * 100
        }

    return {
        'total_babies_with_kmc': total_babies,
        'avg_time_to_initiation_hours': avg_time,
        'within_24h_count': within_24h,
        'within_24h_percentage': (within_24h / total_babies * 100),
        'within_48h_count': within_48h,
        'within_48h_percentage': (within_48h / total_babies * 100),
        'initiation_data': initiation_data,
        'inborn_stats': calc_stats(inborn_data),
        'outborn_stats': calc_stats(outborn_data),
        'inborn_location_stats': {},
        'inborn_location_hospital_stats': {},
        'hospital_stats': {}
    }


def calculate_average_kmc_by_location(baby_data, start_date, end_date):
    """Calculate average KMC hours by location and hospital for time period"""
    location_hospital_data = {}
    
    for baby in baby_data:
        hospital = baby.get('hospitalName', 'Unknown')
        location = baby.get('currentLocationOfTheBaby', 'Unknown')
        birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
        
        if not birth_date:
            continue
            
        key = f"{hospital}-{location}"
        if key not in location_hospital_data:
            location_hospital_data[key] = {
                'hospital': hospital, 'location': location,
                'total_kmc_minutes': 0, 'observation_days': 0, 'baby_count': 0
            }
        
        baby_has_kmc_in_period = False
        
        # New Structure: Check age_days
        age_days = baby.get('age_days', [])
        for day in age_days:
            day_date_ts = day.get('ageDayDate')
            if day_date_ts:
                day_date = convert_unix_to_datetime(day_date_ts).date()
                if start_date <= day_date <= end_date:
                    kmc_minutes = day.get('totalKMCToday', 0)
                    if kmc_minutes > 0:
                         location_hospital_data[key]['total_kmc_minutes'] += kmc_minutes
                         location_hospital_data[key]['observation_days'] += 1
                         baby_has_kmc_in_period = True

        # Legacy Structure Support
        if not age_days and 'observationDay' in baby:
            for obs_day in baby.get('observationDay', []):
                if obs_day.get('ageDay') is None:
                    continue
                obs_date = birth_date.date() + timedelta(days=obs_day.get('ageDay', 0))
                if start_date <= obs_date <= end_date:
                    kmc_minutes = obs_day.get('totalKMCtimeDay', 0)
                    if kmc_minutes > 0:
                        location_hospital_data[key]['total_kmc_minutes'] += kmc_minutes
                        location_hospital_data[key]['observation_days'] += 1
                        baby_has_kmc_in_period = True
        
        if baby_has_kmc_in_period:
            location_hospital_data[key]['baby_count'] += 1
    
    result_data = []
    for key, data in location_hospital_data.items():
        if data['observation_days'] > 0:
            result_data.append({
                'hospital': data['hospital'],
                'location': data['location'],
                'avg_hours_per_day': data['total_kmc_minutes'] / data['observation_days'] / 60,
                'avg_hours_per_baby': data['total_kmc_minutes'] / data['baby_count'] / 60 if data['baby_count'] > 0 else 0,
                'baby_count': data['baby_count'],
                'observation_days': data['observation_days']
            })
    
    return result_data


@st.cache_data(show_spinner=False, ttl=900)
def calculate_discharge_outcomes(baby_data, discharge_data):
    """Calculate discharge outcomes using hierarchical approach"""
    selected_baby_uids = {baby.get('UID') for baby in baby_data if baby.get('UID')}
    discharge_categories = {
        'critical_home': {'count': 0, 'babies': []},
        'stable_home': {'count': 0, 'babies': []},
        'critical_referred': {'count': 0, 'babies': []},
        'died': {'count': 0, 'babies': []},
        'other': {'count': 0, 'babies': []}
    }
    processed_uids = set()

    for discharge in discharge_data:
        uid = discharge.get('UID')
        if not uid or uid in processed_uids or uid not in selected_baby_uids:
            continue
        processed_uids.add(uid)
        category = categorize_discharge(discharge, 'discharges')
        discharge_categories[category]['count'] += 1

    total_discharged = sum(cat['count'] for cat in discharge_categories.values())
    
    return {
        'categories': discharge_categories,
        'total_discharged': total_discharged,
        'unique_babies_processed': len(processed_uids)
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_followup_metrics(followup_data, baby_data):
    """Calculate follow-up completion metrics"""
    processed_uids = set()
    followup_requirements = {
        'Follow up 2': {'followup_number': 2},
        'Follow up 7': {'followup_number': 7},
        'Follow up 14': {'followup_number': 14},
        'Follow up 28': {'followup_number': 28}
    }
    hospital_stats = {}
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids or baby.get('deadBaby') == True:
            continue
        processed_uids.add(uid)
        
        hospital = baby.get('hospitalName', 'Unknown')
        if hospital not in hospital_stats:
            hospital_stats[hospital] = {name: {'eligible': 0, 'completed': 0} for name in followup_requirements}
        
        followup_array = baby.get('followUp', [])
        for followup_name, req in followup_requirements.items():
            hospital_stats[hospital][followup_name]['eligible'] += 1
            for entry in followup_array:
                if entry.get('followUpNumber') == req['followup_number']:
                    hospital_stats[hospital][followup_name]['completed'] += 1
                    break
    
    followup_summary = []
    for hospital, followups in hospital_stats.items():
        for followup_name, stats in followups.items():
            if stats['eligible'] > 0:
                followup_summary.append({
                    'hospital': hospital,
                    'followup_type': followup_name,
                    'eligible': stats['eligible'],
                    'completed': stats['completed'],
                    'completion_rate': stats['completed'] / stats['eligible'] * 100
                })
    
    total_eligible = sum(item['eligible'] for item in followup_summary)
    total_completed = sum(item['completed'] for item in followup_summary)
    
    return {
        'followup_types': list(followup_requirements.keys()),
        'total_eligible': total_eligible,
        'total_completed': total_completed,
        'overall_completion_rate': (total_completed / total_eligible * 100) if total_eligible > 0 else 0,
        'hospital_summary': followup_summary,
        'unique_babies_processed': len(processed_uids)
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_hospital_stay_duration(baby_data):
    """Calculate average hospital stay duration by location"""
    processed_uids = set()
    stay_data = []

    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)

        birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
        if not birth_date:
            continue

        discharge_date = None
        source = baby.get('source', '')
        if source == 'baby' and baby.get('lastDischargeDate'):
            discharge_date = convert_unix_to_datetime(baby.get('lastDischargeDate'))
        elif source == 'babyBackUp' and baby.get('dischargeDate'):
            discharge_date = convert_unix_to_datetime(baby.get('dischargeDate'))

        if discharge_date and discharge_date > birth_date:
            stay_duration = (discharge_date - birth_date).total_seconds() / (24 * 3600)
            stay_data.append({
                'UID': uid,
                'hospital': baby.get('hospitalName', 'Unknown'),
                'location': baby.get('currentLocationOfTheBaby', 'Unknown'),
                'stay_duration_days': stay_duration
            })

    location_stats = {}
    for record in stay_data:
        location = record['location']
        if location not in location_stats:
            location_stats[location] = {'durations': [], 'count': 0, 'total_days': 0}
        location_stats[location]['durations'].append(record['stay_duration_days'])
        location_stats[location]['count'] += 1
        location_stats[location]['total_days'] += record['stay_duration_days']

    for location, stats in location_stats.items():
        if stats['count'] > 0:
            avg = stats['total_days'] / stats['count']
            stats['avg_days'] = avg
            stats['avg_formatted'] = f"{int(avg)} days {int((avg - int(avg)) * 24)} hours"

    return {
        'location_stats': location_stats,
        'raw_data': stay_data,
        'total_babies': len(stay_data)
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_death_rates(baby_data, discharge_data):
    """Calculate comprehensive death rate KPIs and analysis"""
    processed_uids = set()
    hospital_deaths = {}
    hospital_totals = {}
    
    inborn_total, inborn_deaths = 0, 0
    outborn_total, outborn_deaths = 0, 0
    
    dead_uids = set() # Track dead babies for further analysis
    
    # KMC Stability for dead babies
    kmc_stable_total, kmc_stable_deaths = 0, 0
    kmc_unstable_total, kmc_unstable_deaths = 0, 0
    
    # Neonatal vs Infant
    neonatal_deaths = 0
    infant_deaths = 0
    
    # Location Analysis
    location_deaths = {}
    location_totals = {}
    
    # Discharge Outcomes for Dead Babies
    discharge_outcomes_dead = {
        'critical_home': {'count': 0, 'babies': []},
        'stable_home': {'count': 0, 'babies': []},
        'critical_referred': {'count': 0, 'babies': []},
        'died': {'count': 0, 'babies': []},
        'other': {'count': 0, 'babies': []}
    }
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid or uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        hospital = baby.get('hospitalName', 'Unknown')
        is_dead = baby.get('deadBaby') == True
        if is_dead:
            dead_uids.add(uid)
        
        # Hospital stats
        hospital_totals[hospital] = hospital_totals.get(hospital, 0) + 1
        if is_dead:
            hospital_deaths[hospital] = hospital_deaths.get(hospital, 0) + 1
        
        # Inborn/Outborn stats
        place_of_delivery = baby.get('placeOfDelivery', '')
        if place_of_delivery in ['यह अस्पताल', 'this hospital']:
            inborn_total += 1
            if is_dead:
                inborn_deaths += 1
        else:
            outborn_total += 1
            if is_dead:
                outborn_deaths += 1
                
        # Location stats
        location = baby.get('currentLocationOfTheBaby', 'Unknown')
        location_totals[location] = location_totals.get(location, 0) + 1
        if is_dead:
            location_deaths[location] = location_deaths.get(location, 0) + 1
            
        # KMC Stability
        stability = check_kmc_stability(baby)
        if stability == 'stable':
            kmc_stable_total += 1
            if is_dead:
                kmc_stable_deaths += 1
        else:
            kmc_unstable_total += 1
            if is_dead:
                kmc_unstable_deaths += 1
                
        # Neonatal/Infant stats (only for dead babies)
        if is_dead:
            date_of_birth = convert_unix_to_datetime(baby.get('dateOfBirth'))
            date_of_death = convert_unix_to_datetime(baby.get('dateOfDeath'))
            
            if date_of_birth and date_of_death:
                age_days = (date_of_death - date_of_birth).days
                if age_days <= 28:
                    neonatal_deaths += 1
                else:
                    infant_deaths += 1
    
    # Discharge categorization for dead babies
    # Hierarchical processing: Discharges -> Baby -> BabyBackup
    processed_discharge_uids_dead = set()
    
    # 1. Check discharges collection
    for discharge in discharge_data:
        uid = discharge.get('UID')
        if uid in dead_uids and uid not in processed_discharge_uids_dead:
            category = categorize_discharge(discharge, 'discharges')
            discharge_outcomes_dead[category]['count'] += 1
            discharge_outcomes_dead[category]['babies'].append(discharge)
            processed_discharge_uids_dead.add(uid)
            
    # 2. Check baby/backup collection (already in baby_data list)
    for baby in baby_data:
        uid = baby.get('UID')
        if uid in dead_uids and uid not in processed_discharge_uids_dead and baby.get('discharged'):
            source = baby.get('source', '')
            if source == 'baby':
                category = categorize_discharge(baby, 'baby')
            elif source == 'babyBackUp':
                 category = categorize_discharge(baby, 'babyBackUp')
            else:
                continue
                
            discharge_outcomes_dead[category]['count'] += 1
            discharge_outcomes_dead[category]['babies'].append(baby)
            processed_discharge_uids_dead.add(uid)

    total_babies = len(processed_uids)
    dead_babies = len(dead_uids)
    
    # Ensure consistent ordering for hospital data
    all_hospitals = sorted(list(hospital_totals.keys()))
    deaths_list = [hospital_deaths.get(h, 0) for h in all_hospitals]
    totals_list = [hospital_totals.get(h, 0) for h in all_hospitals]
    rates_list = [(d / t * 100) if t > 0 else 0 for d, t in zip(deaths_list, totals_list)]

    return {
        'total_babies': total_babies,
        'dead_babies': dead_babies,
        'mortality_rate': (dead_babies / total_babies * 100) if total_babies > 0 else 0,
        'hospital_data': {
            'hospitals': all_hospitals,
            'totals': totals_list,
            'deaths': deaths_list,
            'rates': rates_list
        },
        'birth_place': {
            'inborn': {'total': inborn_total, 'deaths': inborn_deaths},
            'outborn': {'total': outborn_total, 'deaths': outborn_deaths}
        },
        'location_analysis': {
            loc: {'total': location_totals[loc], 'deaths': location_deaths.get(loc, 0)} for loc in location_totals
        },
        'kmc_stability': {
            'stable': {'total': kmc_stable_total, 'deaths': kmc_stable_deaths},
            'unstable': {'total': kmc_unstable_total, 'deaths': kmc_unstable_deaths}
        },
        'neonatal_vs_infant': {
            'neonatal': {'deaths': neonatal_deaths},
            'infant': {'deaths': infant_deaths}
        },
        'discharge_outcomes': {
            'categories': discharge_outcomes_dead,
            'total_discharged': sum(cat['count'] for cat in discharge_outcomes_dead.values())
        }
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_comprehensive_hospital_mortality(baby_data, discharge_data):
    """Calculate detailed hospital-wise mortality breakdown"""
    hospital_data = {}
    processed_discharge_uids = set()
    
    # Helper to init hospital struct
    def get_hospital_struct():
        return {
            'total_babies': 0,
            'total_deaths': 0,
            'dead_inborn_babies': 0,
            'dead_outborn_babies': 0,
            'discharge_categories': {
                'critical_home': 0, 'stable_home': 0, 'critical_referred': 0, 'died': 0, 'other': 0
            },
            'dead_kmc_stable': 0,
            'dead_kmc_unstable': 0
        }

    # First pass: Basic stats from babies
    for baby in baby_data:
        hospital = baby.get('hospitalName', 'Unknown')
        if hospital not in hospital_data:
            hospital_data[hospital] = get_hospital_struct()
            
        hospital_data[hospital]['total_babies'] += 1
        
        if baby.get('deadBaby') == True:
            hospital_data[hospital]['total_deaths'] += 1
            
            # Inborn/Outborn
            if baby.get('placeOfDelivery') in ['यह अस्पताल', 'this hospital']:
                hospital_data[hospital]['dead_inborn_babies'] += 1
            else:
                hospital_data[hospital]['dead_outborn_babies'] += 1
                
            # KMC Stability
            if check_kmc_stability(baby) == 'unstable':
                hospital_data[hospital]['dead_kmc_unstable'] += 1
            else:
                hospital_data[hospital]['dead_kmc_stable'] += 1
    
    # Second pass: Discharge categories for dead babies (Hierarchical)
    # 1. Discharges Collection
    for discharge in discharge_data:
        uid = discharge.get('UID')
        if not uid or uid in processed_discharge_uids:
            continue
            
        # Find matching baby (must be dead)
        matching_baby = next((b for b in baby_data if b.get('UID') == uid and b.get('deadBaby')), None)
        if matching_baby:
            processed_discharge_uids.add(uid)
            hospital = matching_baby.get('hospitalName', 'Unknown')
            if hospital not in hospital_data:
               hospital_data[hospital] = get_hospital_struct() # Should exist from pass 1 but safety check
            
            category = categorize_discharge(discharge, 'discharges')
            hospital_data[hospital]['discharge_categories'][category] += 1

    # 2. Baby Collection
    for baby in baby_data:
        uid = baby.get('UID')
        if uid in processed_discharge_uids or baby.get('deadBaby') != True:
            continue
            
        if baby.get('discharged') and baby.get('source') == 'baby':
            processed_discharge_uids.add(uid)
            hospital = baby.get('hospitalName', 'Unknown')
            category = categorize_discharge(baby, 'baby')
            hospital_data[hospital]['discharge_categories'][category] += 1

    # 3. BabyBackUp Collection
    for baby in baby_data:
        uid = baby.get('UID')
        if uid in processed_discharge_uids or baby.get('deadBaby') != True:
            continue
            
        if baby.get('discharged') and baby.get('source') == 'babyBackUp':
            processed_discharge_uids.add(uid)
            hospital = baby.get('hospitalName', 'Unknown')
            category = categorize_discharge(baby, 'babyBackUp')
            hospital_data[hospital]['discharge_categories'][category] += 1
            
    return hospital_data


@st.cache_data(show_spinner=False, ttl=900)
def calculate_detailed_mortality_list(baby_data, discharge_data):
    """Generate detailed list of dead babies with comprehensive attributes"""
    all_dead_babies = []
    processed_uids = set()
    
    for baby in baby_data:
        uid = baby.get('UID')
        if baby.get('deadBaby') == True and uid and uid not in processed_uids:
            processed_uids.add(uid)
            
            # Find matching discharge record
            matching_discharge = next((d for d in discharge_data if d.get('UID') == uid), None)
            
            # Calculate metrics
            birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
            registration_date = convert_unix_to_datetime(baby.get('registrationDate'))
            discharge_date = convert_unix_to_datetime(baby.get('dischargeDate') or baby.get('lastDischargeDate'))
            
            # KMC Stats
            total_kmc_minutes = 0
            kmc_days = 0
            first_kmc_start = None
            
            # KMC Stats
            total_kmc_minutes = 0
            kmc_days = 0
            first_kmc_start = None
            
            # New structure
            age_days = baby.get('age_days', [])
            kmc_sessions = baby.get('kmc_sessions', [])
            
            # Calculate total KMC from age days
            for day in age_days:
                mins = day.get('totalKMCToday', 0)
                if mins > 0:
                    total_kmc_minutes += mins
                    kmc_days += 1
                    
            # Get earliest start from sessions
            for session in kmc_sessions:
                ts = convert_unix_to_datetime(session.get('kmcStart'))
                if ts and (first_kmc_start is None or ts < first_kmc_start):
                    first_kmc_start = ts

            # Legacy fallback
            if not age_days and 'observationDay' in baby:
                for obs in baby.get('observationDay', []):
                    mins = obs.get('totalKMCtimeDay', 0) 
                    if mins > 0:
                        total_kmc_minutes += mins
                        kmc_days += 1
                    
                    # Check start times
                    for session in obs.get('timeInKMC', []):
                        ts = convert_unix_to_datetime(session.get('timeStartKMC'))
                        if ts and (first_kmc_start is None or ts < first_kmc_start):
                            first_kmc_start = ts

            # Derived fields
            hours_to_kmc_start = 'N/A'
            if birth_date and first_kmc_start:
                diff = (first_kmc_start - birth_date).total_seconds() / 3600
                hours_to_kmc_start = f"{diff:.1f}h"

            avg_kmc_per_day = (total_kmc_minutes / 60 / kmc_days) if kmc_days > 0 else 0
            
            hospital_stay = 'N/A'
            if discharge_date and birth_date:
                hospital_stay = (discharge_date.date() - birth_date.date()).days
                
            # Hierarchical fields
            # Discharge Category
            category_result = 'other'
            if matching_discharge:
                category_result = categorize_discharge(matching_discharge, 'discharges')
            elif baby.get('discharged') and baby.get('source') == 'baby':
                category_result = categorize_discharge(baby, 'baby')
            elif baby.get('discharged') and baby.get('source') == 'babyBackUp':
                category_result = categorize_discharge(baby, 'babyBackUp')
                
            category_map = {
                'critical_home': 'Critical & Home',
                'stable_home': 'Stable & Home', 
                'critical_referred': 'Critical & Referred',
                'died': 'Died', 
                'other': 'Other'
            }
            
            # Cause of Death priority
            cause_of_death = 'N/A'
            if matching_discharge:
                 cause_of_death = matching_discharge.get('causeOfDeath', matching_discharge.get('causeofDeath', 'N/A'))
            if cause_of_death == 'N/A':
                cause_of_death = baby.get('causeofDeath', baby.get('causeOfDeath', baby.get('deathReason', 'N/A')))
            
            date_of_death = baby.get('dateOfDeath', 'N/A')
            if date_of_death != 'N/A':
                 dod_dt = convert_unix_to_datetime(date_of_death)
                 date_of_death = dod_dt.strftime('%Y-%m-%d') if dod_dt else date_of_death

            all_dead_babies.append({
                'UID': uid,
                'Hospital': baby.get('hospitalName', 'Unknown'),
                'Mother Name': baby.get('motherName', 'N/A'),
                'DOB': birth_date.strftime('%Y-%m-%d') if birth_date else 'Invalid',
                'Gestational Age String': baby.get('gestationalAgeString', 'N/A'),
                'Birth Weight (g)': baby.get('birthWeight', 'N/A'),
                'Registration Weight (g)': baby.get('weightAdmissionMoment', 'N/A'),
                'Discharge Weight (g)': get_prioritized_discharge_weight(baby, matching_discharge),
                'Discharge Temperature (°F)': str(get_prioritized_discharge_temperature(baby, matching_discharge)),
                'Discharge RR (bpm)': get_prioritized_discharge_rr(baby, matching_discharge),
                'Inborn/Outborn': 'Inborn' if baby.get('placeOfDelivery') in ['यह अस्पताल', 'this hospital'] else 'Outborn',
                'Hospital Stay (days)': hospital_stay,
                'Hours to KMC Start': hours_to_kmc_start,
                'KMC Started': 'Yes' if total_kmc_minutes > 0 else 'No',
                'Total KMC Hours': f"{total_kmc_minutes / 60:.1f}h",
                'Avg KMC Hours/Day': f"{avg_kmc_per_day:.1f}h",
                'KMC Status': check_kmc_stability(baby).capitalize(),
                'Feed Mode': get_prioritized_feed_mode(baby, matching_discharge),
                'Breastfeeding Issues Baby': baby.get('breastfeedingIssuesBaby', 'N/A'),
                'Breastfeeding Issues Mother': baby.get('brestfeedingIssuesMother', 'N/A'),
                'Last Danger': baby.get('lastDanger', 'N/A'),
                'How Baby Health': get_prioritized_baby_health(baby, matching_discharge),
                'Readmission Status': 'Yes' if baby.get('idBabyReadmit') else 'No',
                'Date of Death': date_of_death,
                'Cause of Death': cause_of_death,
                'Where Baby Died': baby.get('whereBabyDied', 'N/A'),
                'Why Baby Referred': matching_discharge.get('whyReferred', 'N/A') if matching_discharge else baby.get('whyBabyReferred', 'N/A'),
                'Current Location': baby.get('currentLocationOfTheBaby', 'Unknown'),
                'Critical Reason': get_prioritized_critical_reasons(baby, matching_discharge),
                'Discharge Reason': get_prioritized_discharge_reason(baby, matching_discharge),
                'Discharge Status': category_map.get(category_result, 'Other')
            })
            
    return all_dead_babies


def calculate_daily_kmc_analysis(baby_data, discharge_data=None):
    """Calculate daily KMC analysis for last 7 days"""
    from dashboard_utils import get_hierarchical_discharge_date
    
    today = datetime.now().date()
    analysis_data = {}
    hospitals = sorted(list(set(baby.get('hospitalName') for baby in baby_data if baby.get('hospitalName'))))
    locations = sorted(list(set(baby.get('currentLocationOfTheBaby') for baby in baby_data if baby.get('currentLocationOfTheBaby'))))

    for day_offset in range(1, 8):
        target_date = today - timedelta(days=day_offset)
        date_key = target_date.strftime('%Y-%m-%d')
        analysis_data[date_key] = {h: {l: {'total_kmc_minutes': 0, 'baby_count': 0, 'average_kmc_hours': 0} for l in locations} for h in hospitals}

        for baby in baby_data:
            if baby.get('hospitalName') not in hospitals or baby.get('currentLocationOfTheBaby') not in locations:
                continue
            
            birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
            if not birth_date:
                continue

            # New Structure: Use age_days
            age_days = baby.get('age_days', [])
            if age_days:
                for day in age_days:
                    kmc_time = day.get('totalKMCToday', 0)
                    if kmc_time > 0:
                        day_date_ts = day.get('ageDayDate')
                        if day_date_ts:
                            day_date = convert_unix_to_datetime(day_date_ts).date()
                            date_str = day_date.strftime('%Y-%m-%d')
                            
                            if date_str in analysis_data:
                                hospital = baby['hospitalName']
                                location = baby['currentLocationOfTheBaby']
                                
                                if location in analysis_data[date_str][hospital]:
                                    analysis_data[date_str][hospital][location]['total_kmc_minutes'] += kmc_time
                                    analysis_data[date_str][hospital][location]['baby_count'] += 1

            # Legacy fallback
            elif 'observationDay' in baby:
                 for obs_day in baby.get('observationDay', []):
                    if obs_day.get('totalKMCtimeDay', 0) <= 0:
                        continue
                    
                    time_in_kmc_array = obs_day.get('timeInKMC', [])
                    if time_in_kmc_array:
                        for session in time_in_kmc_array:
                            if isinstance(session, dict):
                                time_start_kmc = session.get('timeStartKMC')
                                if time_start_kmc:
                                    session_start_time = convert_unix_to_datetime(time_start_kmc)
                                    if session_start_time and session_start_time.date() == target_date:
                                        hospital = baby['hospitalName']
                                        location = baby['currentLocationOfTheBaby']
                                        analysis_data[date_key][hospital][location]['total_kmc_minutes'] += obs_day.get('totalKMCtimeDay', 0)
                                        analysis_data[date_key][hospital][location]['baby_count'] += 1
                                        break

        for hospital in hospitals:
            for location in locations:
                data = analysis_data[date_key][hospital][location]
                if data['baby_count'] > 0:
                    data['average_kmc_hours'] = round(data['total_kmc_minutes'] / data['baby_count'] / 60, 1)

    return analysis_data, hospitals, locations, {}


@st.cache_data(show_spinner=False, ttl=900)
def calculate_skin_contact_metrics(baby_data):
    """Calculate skin contact (KMC adherence) metrics from follow-up data"""
    from dashboard_utils import convert_unix_to_datetime
    
    total_babies = 0
    total_skin_contacts = 0
    all_contacts = []
    
    for baby in baby_data:
        followup_array = baby.get('followUp', [])
        if not followup_array:
            continue
            
        baby_contacts = []
        for followup in followup_array:
            if not isinstance(followup, dict):
                continue
            # Count follow-ups 2, 7, 14 (exclude 28)
            followup_number = followup.get('followUpNumber')
            if followup_number in [2, 7, 14]:
                skin_contact = followup.get('numberSkinContact')
                if skin_contact and isinstance(skin_contact, (int, float)) and skin_contact > 0:
                    baby_contacts.append(skin_contact)
        
        if baby_contacts:
            total_babies += 1
            all_contacts.extend(baby_contacts)
    
    if not all_contacts:
        return {
            'total_babies_with_data': 0,
            'average_skin_contact': 0,
            'min_skin_contact': 0,
            'max_skin_contact': 0
        }
    
    return {
        'total_babies_with_data': total_babies,
        'average_skin_contact': sum(all_contacts) / len(all_contacts),
        'min_skin_contact': min(all_contacts),
        'max_skin_contact': max(all_contacts)
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_individual_critical_reasons(baby_data, discharge_data):
    """Calculate individual critical reasons from discharge data"""
    from dashboard_utils import convert_unix_to_datetime
    
    selected_baby_uids = {baby.get('UID') for baby in baby_data if baby.get('UID')}
    individual_reasons = {}
    total_babies_with_reasons = 0
    
    for discharge in discharge_data:
        uid = discharge.get('UID')
        if not uid or uid not in selected_baby_uids:
            continue
            
        critical_reasons = discharge.get('criticalReasons', [])
        if not critical_reasons:
            # Try alternative field names
            critical_reasons = discharge.get('dischargeReason', [])
        
        if critical_reasons:
            if isinstance(critical_reasons, str):
                critical_reasons = [critical_reasons]
            
            has_reason = False
            for reason in critical_reasons:
                if reason and isinstance(reason, str):
                    reason = reason.strip()
                    if reason:
                        if reason not in individual_reasons:
                            individual_reasons[reason] = {'count': 0}
                        individual_reasons[reason]['count'] += 1
                        has_reason = True
            
            if has_reason:
                total_babies_with_reasons += 1
    
    return {
        'total_babies_with_reasons': total_babies_with_reasons,
        'total_unique_reasons': len(individual_reasons),
        'individual_reasons': individual_reasons
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_discharged_babies_without_kmc(baby_data, discharge_data):
    """Calculate discharged babies who received no KMC"""
    from dashboard_utils import convert_unix_to_datetime
    
    hospital_data = {}
    total_discharged = 0
    total_without_kmc = 0
    
    # Build set of discharged UIDs from discharge_data
    discharged_uids = {d.get('UID') for d in discharge_data if d.get('UID')}
    
    for baby in baby_data:
        uid = baby.get('UID')
        if not uid:
            continue
            
        # Check if baby is discharged (from discharge collection or baby record)
        is_discharged = uid in discharged_uids or baby.get('discharged') == True
        if not is_discharged:
            continue
            
        hospital = baby.get('hospitalName', 'Unknown')
        if hospital not in hospital_data:
            hospital_data[hospital] = {
                'total_discharged': 0,
                'without_kmc': 0,
                'babies_without_kmc': [],
                'percentage_without_kmc': 0
            }
        
        hospital_data[hospital]['total_discharged'] += 1
        total_discharged += 1
        
        # Check if baby had any KMC
        has_kmc = False
        for obs_day in baby.get('observationDay', []):
            if obs_day.get('totalKMCtimeDay', 0) > 0:
                has_kmc = True
                break
        
        if not has_kmc:
            hospital_data[hospital]['without_kmc'] += 1
            total_without_kmc += 1
            hospital_data[hospital]['babies_without_kmc'].append({
                'UID': uid,
                'hospitalName': hospital,
                'birthWeight': baby.get('birthWeight', 'N/A'),
                'dischargeDate': baby.get('dischargeDate') or baby.get('lastDischargeDate')
            })
    
    # Calculate percentages
    for hospital, data in hospital_data.items():
        if data['total_discharged'] > 0:
            data['percentage_without_kmc'] = (data['without_kmc'] / data['total_discharged']) * 100
    
    overall_percentage = (total_without_kmc / total_discharged * 100) if total_discharged > 0 else 0
    
    return {
        'total_discharged': total_discharged,
        'total_without_kmc': total_without_kmc,
        'overall_percentage': overall_percentage,
        'hospital_data': hospital_data
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_nurse_activity(baby_data, discharge_data, start_date, end_date, selected_hospitals=None):
    """
    Calculate nurse activity metrics (Follow-ups, Discharges, Registrations)
    using hierarchical logic for discharges to prevent double counting.
    """
    from dashboard_utils import convert_unix_to_datetime
    
    nurse_analysis = {}
    
    # Process Follow-ups
    follow_up_numbers = [1, 2, 3, 7, 14, 28]
    
    for baby in baby_data:
        if not isinstance(baby, dict): continue
            
        follow_up_array = baby.get('followUp', [])
        if not follow_up_array: continue
            
        nurse_name = baby.get('nurseName', 'Not specified')
        hospital = baby.get('hospitalName', 'Unknown')
        
        if nurse_name != 'Not specified':
            key = f"{nurse_name}|{hospital}"
            if key not in nurse_analysis:
                nurse_analysis[key] = {
                    'nurseName': nurse_name, 'hospital': hospital,
                    'followUps': 0, 'discharges': 0, 'registrations': 0
                }
            
            for entry in follow_up_array:
                if not isinstance(entry, dict): continue
                if entry.get('followUpNumber') in follow_up_numbers:
                    f_date = convert_unix_to_datetime(entry.get('date') or entry.get('followUpDate'))
                    if f_date and start_date <= f_date.date() <= end_date:
                        if not selected_hospitals or hospital in selected_hospitals:
                            nurse_analysis[key]['followUps'] += 1

    # Process Registrations (from BOTH baby and babyBackUp)
    for baby in baby_data:
        if not isinstance(baby, dict): continue
        
        nurse_name = baby.get('nurseName', 'Not specified')
        hospital = baby.get('hospitalName', 'Unknown')
        
        if nurse_name != 'Not specified':
            key = f"{nurse_name}|{hospital}"
            if key not in nurse_analysis:
                nurse_analysis[key] = {
                    'nurseName': nurse_name, 'hospital': hospital,
                    'followUps': 0, 'discharges': 0, 'registrations': 0
                }
            
            reg_date = convert_unix_to_datetime(baby.get('registrationDate'))
            if reg_date and start_date <= reg_date.date() <= end_date:
                nurse_analysis[key]['registrations'] += 1

    # Process Discharges (Hierarchical)
    processed_discharge_uids = set()
    discharge_counts = {'discharge_collection': 0, 'baby_collection': 0, 'babybackup_collection': 0}

    # 1. Discharges Collection (Highest Priority)
    for discharge in discharge_data:
        uid = discharge.get('UID')
        if not uid or uid in processed_discharge_uids: continue
        
        discharge_nurse = discharge.get('dischargeNurseName', 'Not specified')
        hospital = discharge.get('hospitalName', 'Unknown')
        discharge_date = convert_unix_to_datetime(discharge.get('dischargeDate'))
        
        if discharge_nurse != 'Not specified':
            if not discharge_date or start_date <= discharge_date.date() <= end_date:
                if not selected_hospitals or hospital in selected_hospitals:
                    key = f"{discharge_nurse}|{hospital}"
                    if key not in nurse_analysis:
                        nurse_analysis[key] = {
                            'nurseName': discharge_nurse, 'hospital': hospital,
                            'followUps': 0, 'discharges': 0, 'registrations': 0
                        }
                    nurse_analysis[key]['discharges'] += 1
                    processed_discharge_uids.add(uid)
                    discharge_counts['discharge_collection'] += 1

    # 2. Baby Collection (Fallback)
    for baby in baby_data:
        if baby.get('source') != 'baby': continue
        uid = baby.get('UID')
        if not uid or uid in processed_discharge_uids: continue
        
        if baby.get('discharged'):
            nurse_name = baby.get('nurseName', 'Not specified')
            hospital = baby.get('hospitalName', 'Unknown')
            d_date = convert_unix_to_datetime(baby.get('lastDischargeDate') or baby.get('dischargeDate'))
            
            if nurse_name != 'Not specified':
                if not d_date or start_date <= d_date.date() <= end_date:
                    if not selected_hospitals or hospital in selected_hospitals:
                        key = f"{nurse_name}|{hospital}"
                        if key not in nurse_analysis:
                             nurse_analysis[key] = {
                                'nurseName': nurse_name, 'hospital': hospital,
                                'followUps': 0, 'discharges': 0, 'registrations': 0
                            }
                        nurse_analysis[key]['discharges'] += 1
                        processed_discharge_uids.add(uid)
                        discharge_counts['baby_collection'] += 1

    # 3. BabyBackUp Collection (Final Fallback)
    for baby in baby_data:
        if baby.get('source') != 'babyBackUp': continue
        uid = baby.get('UID')
        if not uid or uid in processed_discharge_uids: continue
        
        if baby.get('discharged'):
            nurse_name = baby.get('nurseName', 'Not specified')
            hospital = baby.get('hospitalName', 'Unknown')
            d_date = convert_unix_to_datetime(baby.get('dischargeDate') or baby.get('lastDischargeDate'))
            
            if nurse_name != 'Not specified':
                if not d_date or start_date <= d_date.date() <= end_date:
                    if not selected_hospitals or hospital in selected_hospitals:
                        key = f"{nurse_name}|{hospital}"
                        if key not in nurse_analysis:
                             nurse_analysis[key] = {
                                'nurseName': nurse_name, 'hospital': hospital,
                                'followUps': 0, 'discharges': 0, 'registrations': 0
                            }
                        nurse_analysis[key]['discharges'] += 1
                        processed_discharge_uids.add(uid)
                        discharge_counts['babybackup_collection'] += 1
                        
    return nurse_analysis, discharge_counts


@st.cache_data(show_spinner=False, ttl=900)
def calculate_sandbox_system_metrics(baby_data, discharge_data, followup_data, kmc_session_data):
    """
    Calculate SYSTEM metrics for the Sandbox tab based on 'system_monitoring' sheet.
    Metrics 1-14 (Registration, Coverage, Clinical, Follow-up Contactability, Inpatient Exposure).
    Adapted from first_pass/metrics.py
    """
    from dashboard_utils import convert_unix_to_datetime

    # Helper for safe division
    def safe_div(n, d):
        return n / d if d else 0.0

    # 1. Eligibility Filtering
    eligible_babies = []
    eligible_ids = set()

    for baby in baby_data:
        weight = baby.get('birthWeight')
        ga = baby.get('gestationalAge')
        
        is_eligible = False
        if baby.get('babyInProgram'):
            is_eligible = True

        # Check Weight (< 2500g)
        if weight:
            try:
                if float(weight) < 2500:
                    is_eligible = True
            except (ValueError, TypeError):
                pass

        # Check GA (<= 36 weeks)
        if not is_eligible and ga:
            try:
                if float(ga) <= 36:
                    is_eligible = True
            except (ValueError, TypeError):
                pass

        if is_eligible:
            eligible_babies.append(baby)
            uid = baby.get('UID')
            if uid:
                eligible_ids.add(uid)

    # Pre-process data for eligible babies
    # Follow-ups are often nested in baby objects in the new structure, but sometimes passed separately?
    # calculate_followup_metrics uses baby_data.get('followUp', []).
    # The signature here accepts followup_data. Let's assume it might be a flat list or we extract from babies.
    # If followup_data is passed as a list of independent followup records, we filter it.
    
    eligible_followups = []
    
    # If followup_data is empty, try extracting from babies
    if not followup_data:
        for baby in eligible_babies:
            for f in baby.get('followUp', []):
                # Add baby UID to followup for context if missing
                if not f.get('idBaby') and not f.get('UID'):
                    f['UID'] = baby.get('UID') # Use baby UID as link
                eligible_followups.append(f)
    else:
        for f in followup_data:
            # Try to match by UID (if present) or if it has idBaby
            f_uid = f.get('idBaby') or f.get('UID') 
            if f_uid in eligible_ids:
                eligible_followups.append(f)

    eligible_sessions = []
    # If kmc_session_data is empty, try extracting from babies (new structure)
    if not kmc_session_data:
        for baby in eligible_babies:
            # Check kmc_sessions array
            for s in baby.get('kmc_sessions', []):
                 if not s.get('idBaby') and not s.get('UID'):
                    s['UID'] = baby.get('UID')
                 eligible_sessions.append(s)
                 
            # Also check legacy observationDay timeInKMC if needed... 
            # But converting that to sessions format is complex.
            # Let's assume kmc_sessions key is populated by the data loader 
            # (which it seems to be in calculate_kmc_initiation_metrics)
    else:
        for s in kmc_session_data:
             s_uid = s.get('idBaby') or s.get('UID')
             if s_uid in eligible_ids:
                 eligible_sessions.append(s)


    # --- METRICS CALCULATIONS ---

    # 1. Eligible babies registered (Inborn)
    # Definition: Total number of babies born at the hospital who meet criteria.
    # If placeOfDelivery is missing, we assume they are inborn to avoid zero denominator, 
    # as most data in the system is likely from the deployment hospitals.
    inborn_eligible = []
    for b in eligible_babies:
        pod = str(b.get('placeOfDelivery', '')).lower()
        if not pod or pod in ['nan', 'none', 'null', ''] or pod in ['यह अस्पताल', 'this hospital', 'hospital']:
             inborn_eligible.append(b)
             
    m1_registered = len(inborn_eligible)

    # 2. Eligible babies admitted
    # Definition: Total number of eligible babies admitted (All eligible found in system).
    m2_admitted = len(eligible_babies)

    # 3. Total inpatient baby-days
    m3_baby_days = 0
    baby_days_details = {} # Map baby_id -> days (for Metric 13)

    for baby in eligible_babies:
        birth_date = convert_unix_to_datetime(baby.get('dateOfBirth')) # Note key change from birthDate
        discharge_date = None
        
        # Try finding discharge date
        if baby.get('lastDischargeDate'):
             discharge_date = convert_unix_to_datetime(baby.get('lastDischargeDate'))
        elif baby.get('dischargeDate'):
             discharge_date = convert_unix_to_datetime(baby.get('dischargeDate'))

        days = 0
        if birth_date:
            from datetime import datetime
            # Use UTC for now to avoid naive/aware issues if convert_unix_to_datetime returns aware
            now = datetime.now(birth_date.tzinfo) if birth_date.tzinfo else datetime.now()
            
            end_date = discharge_date or now
            days = (end_date - birth_date).days
            days = max(1, days) # Minimum 1 day

        m3_baby_days += days
        baby_id = baby.get('UID')
        if baby_id:
            baby_days_details[baby_id] = days

    # 4. Eligible babies identified
    m4_identified = len(eligible_babies)

    # 5. Coverage of eligibility identification
    m5_coverage = 100.0 

    # 6. Completeness of program registration
    program_registered = [b for b in eligible_babies if b.get('babyInProgram')]
    m6_completeness_num = len(program_registered)
    m6_completeness_pct = safe_div(m6_completeness_num, m4_identified) * 100

    # 7. Early referral or transfer (< 24h)
    early_transfer_count = 0
    for baby in inborn_eligible:
        d_type = str(baby.get('lastDischargeStatus', '')).lower()
        if 'refer' in d_type or 'transfer' in d_type:
             birth_dt = convert_unix_to_datetime(baby.get('dateOfBirth'))
             disch_dt = convert_unix_to_datetime(baby.get('lastDischargeDate'))
             if birth_dt and disch_dt:
                 hours = (disch_dt - birth_dt).total_seconds() / 3600
                 if hours < 24:
                     early_transfer_count += 1

    m7_early_transfer_pct = safe_div(early_transfer_count, m1_registered) * 100

    # 8. Admitted babies not clinically eligible for KMC at 24 hours
    # Approximation: using observations if available, otherwise 0
    # In new dashboard, observations are nested in baby['observations'] usually.
    # We'll skip detailed obs logic for now as it requires complex parsing not present in passed arguments
    # unless we iterate babies.
    m8_unstable_pct = 0.0 
    unstable_24h_count = 0

    # 9-12. Caregiver contactability (Day 7, 14, 21, 28)
    contact_counts = {7: 0, 14: 0, 21: 0, 28: 0}
    due_counts = {7: 0, 14: 0, 21: 0, 28: 0}
    
    for f in eligible_followups:
        num = f.get('followUpNumber')
        status = str(f.get('followUpStatus', '')).lower()
        
        if num in contact_counts:
            due_counts[num] += 1
            if status in ['completed', 'contacted']:
                contact_counts[num] += 1
    
    m9_d7_pct = safe_div(contact_counts[7], due_counts[7]) * 100
    m10_d14_pct = safe_div(contact_counts[14], due_counts[14]) * 100
    m11_d21_pct = safe_div(contact_counts[21], due_counts[21]) * 100
    m12_d28_pct = safe_div(contact_counts[28], due_counts[28]) * 100

    # 13. Distribution of inpatient KMC exposure
    kmc_days_bins = {'0-2h': 0, '2-8h': 0, '8-12h': 0, '12h+': 0}
    
    # Calculate daily KMC for eligible babies
    # Use age_days if available, else sessions
    total_analyzed_days = 0
    from collections import defaultdict
    daily_kmc_map = defaultdict(float) # (bid, date) -> hours

    for s in eligible_sessions:
        bid = s.get('idBaby') or s.get('UID')
        start = convert_unix_to_datetime(s.get('kmcStart'))
        duration = (s.get('kmcDuration') or 0) / 60.0
        if bid and start:
            daily_kmc_map[(bid, start.date())] += duration
            
    # Also check age_days for babies who might not have sessions in the list
    for baby in eligible_babies:
        bid = baby.get('UID')
        if not bid: continue
        
        for day in baby.get('age_days', []):
             mins = day.get('totalKMCToday', 0)
             if mins > 0:
                 if day.get('ageDayDate'):
                     d = convert_unix_to_datetime(day.get('ageDayDate')).date()
                     # Prioritise age_days aggregation
                     daily_kmc_map[(bid, d)] = max(daily_kmc_map[(bid, d)], mins/60.0)

    for baby in eligible_babies:
        bid = baby.get('UID')
        birth_dt = convert_unix_to_datetime(baby.get('dateOfBirth'))
        discharge_dt = convert_unix_to_datetime(baby.get('lastDischargeDate') or baby.get('dischargeDate'))
        
        if not birth_dt: continue
            
        from datetime import datetime
        now = datetime.now(birth_dt.tzinfo) if birth_dt.tzinfo else datetime.now()
        end_dt = discharge_dt or now
        
        curr = birth_dt.date()
        end = end_dt.date()
        from datetime import timedelta
        
        while curr <= end:
            hours = daily_kmc_map.get((bid, curr), 0)
            
            if hours < 2:
                kmc_days_bins['0-2h'] += 1
            elif 2 <= hours < 8:
                kmc_days_bins['2-8h'] += 1
            elif 8 <= hours < 12:
                kmc_days_bins['8-12h'] += 1
            else:
                kmc_days_bins['12h+'] += 1
            
            total_analyzed_days += 1
            curr += timedelta(days=1)
            
    m13_dist = {
        '0-2h': safe_div(kmc_days_bins['0-2h'], total_analyzed_days) * 100,
        '2-8h': safe_div(kmc_days_bins['2-8h'], total_analyzed_days) * 100,
        '8-12h': safe_div(kmc_days_bins['8-12h'], total_analyzed_days) * 100,
        '12h+': safe_div(kmc_days_bins['12h+'], total_analyzed_days) * 100,
    }

    return {
        'm1_registered': m1_registered,
        'm2_admitted': m2_admitted,
        'm3_baby_days': m3_baby_days,
        'm4_identified': m4_identified,
        'm5_coverage_pct': m5_coverage,
        'm5_coverage_num': m4_identified,
        'm5_coverage_denom': m1_registered,
        'm6_completeness_pct': m6_completeness_pct,
        'm6_completeness_num': m6_completeness_num,
        'm6_completeness_denom': m4_identified,
        'm7_early_transfer_pct': m7_early_transfer_pct,
        'm7_early_transfer_num': early_transfer_count,
        'm7_early_transfer_denom': m1_registered,
        'm8_unstable_pct': m8_unstable_pct, 
        'm8_unstable_num': unstable_24h_count,
        'm8_unstable_denom': m2_admitted,
        'm9_d7_pct': m9_d7_pct,
        'm9_d7_num': contact_counts[7],
        'm9_d7_denom': due_counts[7],
        'm10_d14_pct': m10_d14_pct,
        'm10_d14_num': contact_counts[14],
        'm10_d14_denom': due_counts[14],
        'm11_d21_pct': m11_d21_pct,
        'm11_d21_num': contact_counts[21],
        'm11_d21_denom': due_counts[21],
        'm12_d28_pct': m12_d28_pct,
        'm12_d28_num': contact_counts[28],
        'm12_d28_denom': due_counts[28],
        'm13_distribution': m13_dist,
        'm13_counts': kmc_days_bins,
        'm13_total_days': total_analyzed_days,
        'eligible_babies_list': eligible_babies
    }


@st.cache_data(show_spinner=False, ttl=900)
def calculate_sandbox_program_metrics(baby_data, discharge_data, followup_data, kmc_session_data, feeding_data=None, observation_data=None):
    """
    Calculate PROGRAM metrics for the Sandbox tab based on 'program_monitoring' sheet.
    Adapted from first_pass/metrics.py
    """
    from dashboard_utils import convert_unix_to_datetime

    def safe_div(n, d):
        return n / d if d else 0.0

    # 1. Eligibility Filtering
    eligible_babies = []
    eligible_ids = set()

    for baby in baby_data:
        weight = baby.get('birthWeight')
        ga = baby.get('gestationalAge')
        is_eligible = False
        if baby.get('babyInProgram'):
            is_eligible = True
        
        if weight:
            try:
                if float(weight) < 2500: is_eligible = True
            except: pass
        if not is_eligible and ga:
            try:
                if float(ga) <= 36: is_eligible = True
            except: pass

        if is_eligible:
            eligible_babies.append(baby)
            uid = baby.get('UID')
            if uid: eligible_ids.add(uid)

    # Pre-process data
    # Filter sessions and followups
    eligible_sessions = []
    if not kmc_session_data:
         for baby in eligible_babies:
             for s in baby.get('kmc_sessions', []):
                 if not s.get('UID'): s['UID'] = baby.get('UID')
                 eligible_sessions.append(s)
    else:
        for s in kmc_session_data:
             s_uid = s.get('idBaby') or s.get('UID')
             if s_uid in eligible_ids:
                 eligible_sessions.append(s)

    eligible_followups = []
    if not followup_data:
        for baby in eligible_babies:
            for f in baby.get('followUp', []):
                if not f.get('UID'): f['UID'] = baby.get('UID')
                eligible_followups.append(f)
    else:
        for f in followup_data:
             f_uid = f.get('idBaby') or f.get('UID')
             if f_uid in eligible_ids:
                 eligible_followups.append(f)

    # 1. Any KMC Initiation
    babies_with_kmc = set()
    for s in eligible_sessions:
        if (s.get('kmcDuration') or 0) > 0:
            babies_with_kmc.add(s.get('idBaby') or s.get('UID'))
    
    # Also check age_days
    for baby in eligible_babies:
        for day in baby.get('age_days', []):
            if day.get('totalKMCToday', 0) > 0:
                babies_with_kmc.add(baby.get('UID'))

    m1_any_init_num = len(babies_with_kmc)
    m1_any_init_den = len(eligible_babies)
    m1_any_init_pct = safe_div(m1_any_init_num, m1_any_init_den) * 100

    # 2. KMC Initiation < 24h
    babies_init_24h = set()
    baby_first_kmc = {}

    for s in eligible_sessions:
        bid = s.get('idBaby') or s.get('UID')
        start = convert_unix_to_datetime(s.get('kmcStart'))
        if bid and start:
            if bid not in baby_first_kmc or start < baby_first_kmc[bid]:
                baby_first_kmc[bid] = start
    
    # Check age_days too
    for baby in eligible_babies:
        bid = baby.get('UID')
        for day in baby.get('age_days', []):
            if day.get('totalKMCToday', 0) > 0:
                 d = convert_unix_to_datetime(day.get('ageDayDate'))
                 if d:
                     if bid not in baby_first_kmc or d < baby_first_kmc[bid]:
                         baby_first_kmc[bid] = d

    for baby in eligible_babies:
        bid = baby.get('UID')
        birth_dt = convert_unix_to_datetime(baby.get('dateOfBirth'))
        
        if bid in baby_first_kmc and birth_dt:
            first_kmc = baby_first_kmc[bid]
            hours = (first_kmc - birth_dt).total_seconds() / 3600
            if hours <= 24:
                babies_init_24h.add(bid)

    m2_init_24h_num = len(babies_init_24h)
    m2_init_24h_den = len(eligible_babies)
    m2_init_24h_pct = safe_div(m2_init_24h_num, m2_init_24h_den) * 100

    # 3. Mean daily skin-to-skin
    # Recalculate KMC totals
    total_kmc_hours = 0.0
    from collections import defaultdict
    kmc_per_day = defaultdict(float) # (bid, date) -> hours

    for s in eligible_sessions:
        bid = s.get('idBaby') or s.get('UID')
        start = convert_unix_to_datetime(s.get('kmcStart'))
        dur = (s.get('kmcDuration') or 0) / 60.0
        if bid and start:
            kmc_per_day[(bid, start.date())] += dur
            
    for baby in eligible_babies:
        bid = baby.get('UID')
        for day in baby.get('age_days', []):
            mins = day.get('totalKMCToday', 0)
            if mins > 0:
                 d_ts = day.get('ageDayDate')
                 if d_ts:
                     d = convert_unix_to_datetime(d_ts).date()
                     # Prioritise age_days aggregation
                     kmc_per_day[(bid, d)] = max(kmc_per_day[(bid, d)], mins/60.0)

    total_kmc_hours = sum(kmc_per_day.values())
    
    # Total baby days
    total_baby_days = 0
    from datetime import datetime, timedelta
    
    for baby in eligible_babies:
        bid = baby.get('UID')
        birth_dt = convert_unix_to_datetime(baby.get('dateOfBirth'))
        if not birth_dt: continue
        
        discharge_dt = convert_unix_to_datetime(baby.get('lastDischargeDate') or baby.get('dischargeDate'))
        now = datetime.now(birth_dt.tzinfo) if birth_dt.tzinfo else datetime.now()
        end_dt = discharge_dt or now
        
        curr = birth_dt.date()
        end = end_dt.date()
        while curr <= end:
            total_baby_days += 1
            curr += timedelta(days=1)
            
    m3_mean_daily_kmc = safe_div(total_kmc_hours, total_baby_days)

    # 4. Inpatient days with KMC >= 12h
    days_with_12h = 0
    for hours in kmc_per_day.values():
        if hours >= 12:
            days_with_12h += 1
            
    m4_days_12h_pct = safe_div(days_with_12h, total_baby_days) * 100

    # 5. Daily exclusive breastmilk (Placeholder 0% if no detailed feeding data)
    m5_exclusive_pct = 0.0
    exclusive_days = 0

    # 6. Hypothermia < 72h (Placeholder 0% if no detailed obs data)
    m6_hypo_pct = 0.0
    m6_hypo_num = 0
    m6_hypo_den = 0

    # 7. Discharged critical
    critical_count = 0
    discharged_alive_count = 0
    
    for baby in eligible_babies:
        status = str(baby.get('lastDischargeStatus', '')).lower()
        if baby.get('discharged') and not baby.get('deadBaby'):
            if 'refer' not in status and 'transfer' not in status:
                discharged_alive_count += 1
                if 'critical' in status:
                    critical_count += 1
                    
    m7_critical_pct = safe_div(critical_count, discharged_alive_count) * 100

    # 8. Discharge Counselling (Placeholder)
    m8_counselling_score = 0.0

    # 9-12. Follow-up
    fu_d7_contacted, fu_d7_kmc, fu_d7_care = 0, 0, 0
    fu_d28_contacted, fu_d28_kmc, fu_d28_care = 0, 0, 0
    
    for f in eligible_followups:
        num = f.get('followUpNumber')
        status = str(f.get('followUpStatus', '')).lower()
        if status in ['completed', 'contacted']:
            if num == 1 or num == 7: # Accept '1' or '7' as day 7
                fu_d7_contacted += 1
                if (f.get('kmcHoursCount') or f.get('totalKMCTime') or 0) > 0:
                    fu_d7_kmc += 1
                if f.get('readmitted') or f.get('sickVisit'):
                    fu_d7_care += 1
                    
            elif num == 2 or num == 28: # Accept '2' or '28' as day 28
                fu_d28_contacted += 1
                if (f.get('kmcHoursCount') or f.get('totalKMCTime') or 0) > 0:
                    fu_d28_kmc += 1
                if f.get('readmitted') or f.get('sickVisit'):
                    fu_d28_care += 1

    m9_kmc_cont_d7_pct = safe_div(fu_d7_kmc, fu_d7_contacted) * 100
    m10_kmc_cont_d28_pct = safe_div(fu_d28_kmc, fu_d28_contacted) * 100
    m11_care_d7_pct = safe_div(fu_d7_care, fu_d7_contacted) * 100
    m12_care_d28_pct = safe_div(fu_d28_care, fu_d28_contacted) * 100

    # 13. Adverse Events
    m13_adverse_events = 0
    # Requires observation loop. Placeholder.
    
    return {
        'm1_any_init_pct': m1_any_init_pct,
        'm1_any_init_num': m1_any_init_num,
        'm1_any_init_den': m1_any_init_den,
        'm2_init_24h_pct': m2_init_24h_pct,
        'm2_init_24h_num': m2_init_24h_num,
        'm2_init_24h_den': m2_init_24h_den,
        'm3_mean_daily_kmc': m3_mean_daily_kmc,
        'm4_days_12h_pct': m4_days_12h_pct,
        'm4_days_12h_num': days_with_12h,
        'm4_days_12h_den': total_baby_days,
        'm5_exclusive_pct': m5_exclusive_pct,
        'm5_exclusive_num': exclusive_days,
        'm5_exclusive_den': total_baby_days,
        'm6_hypo_pct': m6_hypo_pct,
        'm6_hypo_num': m6_hypo_num,
        'm6_hypo_den': m6_hypo_den,
        'm7_critical_pct': m7_critical_pct,
        'm7_critical_num': critical_count,
        'm7_critical_den': discharged_alive_count,
        'm8_counselling_score': m8_counselling_score,
        'm9_kmc_cont_d7_pct': m9_kmc_cont_d7_pct,
        'm9_kmc_cont_d7_num': fu_d7_kmc, 
        'm9_kmc_cont_d7_den': fu_d7_contacted, 
        'm10_kmc_cont_d28_pct': m10_kmc_cont_d28_pct,
        'm10_kmc_cont_d28_num': fu_d28_kmc, 
        'm10_kmc_cont_d28_den': fu_d28_contacted, 
        'm11_care_d7_pct': m11_care_d7_pct,
        'm11_care_d7_num': fu_d7_care, 
        'm11_care_d7_den': fu_d7_contacted, 
        'm12_care_d28_pct': m12_care_d28_pct,
        'm12_care_d28_num': fu_d28_care, 
        'm12_care_d28_den': fu_d28_contacted, 
        'm13_adverse_events': m13_adverse_events,
        'eligible_babies_list': eligible_babies
    }


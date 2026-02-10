"""
Firebase utilities - initialization, data loading, and query helpers.
"""
import streamlit as st
import json
import os
import time
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import FieldFilter

# --- CONFIGURATION & IMPORTS ---
try:
    from config import USE_FAKE_DATA, FAKE_DATA_DIR, PROJECT_ID
except (ImportError, KeyError):
    # Fallback if config is missing or fails
    USE_FAKE_DATA = False
    FAKE_DATA_DIR = os.path.join(os.path.dirname(__file__), 'testing', 'synthetic_data')


def _load_local_json(filename):
    """Helper to load local JSON for fake data mode"""
    path = os.path.join(FAKE_DATA_DIR, f"{filename}.json")
    if not os.path.exists(path):
        st.warning(f"⚠️ Fake data file not found: {filename}.json")
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure list format
            if isinstance(data, dict):
                data = [data]
            return data
    except Exception as e:
        st.error(f"Error loading {filename}: {e}")
        return []


def _ensure_serializable(obj):
    """Recursively ensure all objects are pickle-serializable - Optimized"""
    if obj is None:
        return None
    # Fast path for common primitives
    if isinstance(obj, (str, int, float, bool)):
        return obj
    # Handle timestamps directly
    if hasattr(obj, 'timestamp'):
        return obj.timestamp()
    # Handle nested structures
    if isinstance(obj, list):
        return [_ensure_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _ensure_serializable(v) for k, v in obj.items()}
    # Fallback
    return str(obj)


@st.cache_resource
def initialize_firebase():
    """Initialize Firebase connection with enhanced reliability"""
    if not firebase_admin._apps:
        try:
            # Try Streamlit secrets first (for deployed version)
            try:
                # Use generic section from secrets.toml
                secret_section = "firestore"
                
                if secret_section in st.secrets:
                    gcp_creds = st.secrets[secret_section]
                else:
                     # Fallback for backward compatibility
                     if "gcp_service_account" in st.secrets:
                         gcp_creds = st.secrets["gcp_service_account"]
                     else:
                        raise KeyError(f"No secrets found for {secret_section}. Please configure [{secret_section}] in .streamlit/secrets.toml")
                
                # Handle private key formatting
                private_key = gcp_creds["private_key"]

                # Clean up private key formatting
                if "\\n" in private_key:
                    private_key = private_key.replace('\\n', '\n')

                # Ensure proper PEM formatting
                if not private_key.startswith('-----BEGIN PRIVATE KEY-----'):
                    private_key = '-----BEGIN PRIVATE KEY-----\n' + private_key
                if not private_key.endswith('-----END PRIVATE KEY-----'):
                    private_key = private_key + '\n-----END PRIVATE KEY-----'

                firebase_key = {
                    "type": gcp_creds["type"],
                    "project_id": gcp_creds["project_id"],
                    "private_key_id": gcp_creds["private_key_id"],
                    "private_key": private_key,
                    "client_email": gcp_creds["client_email"],
                    "client_id": gcp_creds["client_id"],
                    "auth_uri": gcp_creds["auth_uri"],
                    "token_uri": gcp_creds["token_uri"],
                    "auth_provider_x509_cert_url": gcp_creds["auth_provider_x509_cert_url"],
                    "client_x509_cert_url": gcp_creds["client_x509_cert_url"],
                    "universe_domain": gcp_creds.get("universe_domain", "googleapis.com")
                }

                # Initialize Firebase with optimized settings for Streamlit Cloud
                cred = credentials.Certificate(firebase_key)
                app = firebase_admin.initialize_app(cred, {
                    'projectId': gcp_creds["project_id"]
                })

                # st.success("✅ Using Streamlit secrets for Firebase connection")

            except (KeyError, FileNotFoundError, Exception) as e:
                # Fallback to local file (for local development)
                st.info(f"Streamlit secrets not available, trying local file...")
                # Check for any json file that looks like a key
                key_path = 'service-account.json'
                if not os.path.exists(key_path):
                    st.error(f"Firebase key file not found at {key_path}. Please configure Streamlit secrets for deployment.")
                    return None

                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)
                # st.success("✅ Using local Firebase key file for development")

            # Get Firestore client with timeout settings
            db = firestore.client()

            # Test connection
            try:
                # Quick test query to verify connection
                test_query = db.collection('baby').limit(1).get(timeout=10)
                # st.success("🔥 Firebase connection verified successfully!")
            except Exception as test_error:
                st.warning(f"Firebase connected but test query failed: {str(test_error)[:100]}")

            return db

        except Exception as e:
            st.error(f"❌ Firebase initialization failed: {str(e)}")
            st.error("Please check your Firebase configuration and network connection.")
            return None

    # Return existing client
    try:
        db = firestore.client()
        return db
    except Exception as e:
        st.error(f"Failed to get Firestore client: {e}")
        return None


def load_collection_with_retry(collection_name, max_retries=5, show_progress=False):
    """Load full collection with robust retry logic - silent loading"""
    # Get fresh Firebase connection for each collection
    db = initialize_firebase()
    if not db:
        return []

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                # Exponential backoff with jitter
                delay = min(2 ** attempt + (attempt * 0.5), 15)
                time.sleep(delay)
                # Only show retry messages if show_progress is True
                if show_progress:
                    st.info(f"Retrying {collection_name} (attempt {attempt + 1}/{max_retries})...")

            # Load ALL data without artificial limits
            docs = db.collection(collection_name).stream()

            # Convert to serializable dictionaries
            result = []
            doc_count = 0

            for doc in docs:
                try:
                    # Convert Firebase document to plain dict
                    data = doc.to_dict()
                    data['id'] = doc.id

                    # Clean up any non-serializable objects
                    cleaned_data = {}
                    for key, value in data.items():
                        try:
                            # Convert timestamps and other Firebase objects to strings/primitives
                            if hasattr(value, 'timestamp'):  # Firebase timestamp
                                cleaned_data[key] = value.timestamp()
                            elif hasattr(value, 'to_dict'):  # Nested Firebase objects
                                cleaned_data[key] = value.to_dict()
                            else:
                                cleaned_data[key] = value
                        except:
                            # If anything fails, convert to string
                            cleaned_data[key] = str(value)

                    result.append(cleaned_data)
                    doc_count += 1

                except Exception as doc_error:
                    # Silent skip of corrupted documents
                    continue

            # Return results silently
            return result

        except Exception as e:
            error_msg = str(e).lower()
            if attempt < max_retries - 1:
                continue
            else:
                # Only show error on final failure
                if show_progress:
                    st.error(f"❌ Failed to load {collection_name}: {str(e)[:100]}")
                return []

    return []


def load_query_with_retry(query, description="data", max_retries=3):
    """Load Firestore query results with retry logic"""
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(min(2 ** attempt, 5))
                
            docs = query.stream()
            result = []
            
            for doc in docs:
                try:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    # Use our optimized serializer
                    cleaned_data = _ensure_serializable(data)
                    result.append(cleaned_data)
                except:
                    continue
            return result
            
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Error loading {description}: {e}")
                return []
    return []


@st.cache_data(show_spinner="Loading and transforming data...", ttl=900, max_entries=20)
def _reconstruct_baby_structure(babies_data, age_days_data, kmc_sessions_data, observations_data, lr_babies_data):
    """
    Reconstruct the legacy baby structure with embedded observationDay list 
    from the new normalized schema.
    """
    reconstructed_babies = []
    
    # Index helper collections by idBaby for fast lookup
    age_days_by_baby = {}
    for ad in age_days_data:
        bid_ref = ad.get('idBaby', {})
        bid = ''
        if isinstance(bid_ref, dict):
            bid = bid_ref.get('__ref__', '').split('/')[-1]
        elif isinstance(bid_ref, str):
            bid = bid_ref.split('/')[-1]
            
        if bid:
            if bid not in age_days_by_baby: age_days_by_baby[bid] = []
            age_days_by_baby[bid].append(ad)
            
    kmc_sessions_by_baby = {}
    for ks in kmc_sessions_data:
        bid_ref = ks.get('idBaby', {})
        bid = ''
        if isinstance(bid_ref, dict):
            bid = bid_ref.get('__ref__', '').split('/')[-1]
        elif isinstance(bid_ref, str):
            bid = bid_ref.split('/')[-1]

        if bid:
            if bid not in kmc_sessions_by_baby: kmc_sessions_by_baby[bid] = []
            kmc_sessions_by_baby[bid].append(ks)

    observations_by_baby = {}
    for obs in observations_data:
        bid_ref = obs.get('idBaby', {})
        bid = ''
        if isinstance(bid_ref, dict):
            bid = bid_ref.get('__ref__', '').split('/')[-1]
        elif isinstance(bid_ref, str):
            bid = bid_ref.split('/')[-1]

        if bid:
            if bid not in observations_by_baby: observations_by_baby[bid] = []
            observations_by_baby[bid].append(obs)

    for baby in babies_data:
        new_baby = baby.copy()
        
        # 1. Map fields to legacy names
        new_baby['dateOfBirth'] = baby.get('birthDate')
        new_baby['currentLocationOfTheBaby'] = baby.get('lastLocationBaby')
        
        # 2. Construct observationDay list
        formatted_baby_id = baby.get('id') 
        
        obs_days_list = []
        
        # Get all relevant days from ageDays
        relevant_age_days = age_days_by_baby.get(formatted_baby_id, [])
        relevant_kmc = kmc_sessions_by_baby.get(formatted_baby_id, [])
        relevant_obs = observations_by_baby.get(formatted_baby_id, [])
        
        # Find all unique ageDay numbers
        all_day_nums = set()
        for d in relevant_age_days: all_day_nums.add(d.get('ageDayNumber'))
        for k in relevant_kmc: all_day_nums.add(k.get('ageDay'))
        for o in relevant_obs: all_day_nums.add(o.get('ageDay'))
        
        for day_num in sorted([d for d in all_day_nums if d is not None]):
            day_obj = {
                'ageDay': day_num,
                'totalKMCtimeDay': 0,
                'timeInKMC': [],
                'filledCorrectly': None,
                'kmcfilledcorrectly': None,
                'mnecomment': '',
                'date': None
            }
            
            # Merge ageDay data
            day_record = next((d for d in relevant_age_days if d.get('ageDayNumber') == day_num), None)
            if day_record:
                day_obj['totalKMCtimeDay'] = day_record.get('totalKMCToday', 0)
                day_obj['date'] = day_record.get('ageDayDate')

            # Merge KMC sessions
            day_sessions = [k for k in relevant_kmc if k.get('ageDay') == day_num]
            for sess in day_sessions:
                session_obj = {
                    'timeStartKMC': sess.get('kmcStart'),
                    'timeEndKMC': sess.get('kmcEnd'),
                    'duration': sess.get('kmcDuration'),
                    'provider': sess.get('kmcProvider')
                }
                day_obj['timeInKMC'].append(session_obj)

            # Merge Observations
            day_obs = next((o for o in relevant_obs if o.get('ageDay') == day_num), None)
            if day_obs:
                status = day_obs.get('verificationStatus', '').lower()
                if status == 'correct':
                    day_obj['filledCorrectly'] = True
                    day_obj['kmcfilledcorrectly'] = True
                elif status == 'incorrect':
                    day_obj['filledCorrectly'] = False
                    day_obj['kmcfilledcorrectly'] = False
                
                day_obj['mnecomment'] = day_obs.get('verificationNotes', '')
                day_obj['temperature'] = day_obs.get('temperature')
                day_obj['RR'] = day_obs.get('RR')
            
            obs_days_list.append(day_obj)
            
        new_baby['observationDay'] = obs_days_list
        reconstructed_babies.append(new_baby)
        
    return reconstructed_babies


@st.cache_data(show_spinner="Loading filtered data from Firebase...", ttl=900, max_entries=20)
def load_filtered_data_from_firebase(start_date, end_date, uid=None, hospital_names=None):
    """Load ONLY data within the specified date range from Firebase, optionally filtered by UID and Hospitals"""
    start_time = time.time()
    
    # --- FAKE DATA MODE ---
    if USE_FAKE_DATA:
        st.warning("⚠️ USING FAKE DATA MODE (Local JSON)")
        try:
            # Load raw data from JSONs
            baby_docs = _load_local_json('babies')
            lr_docs = _load_local_json('lrBabies')
            age_days_docs = _load_local_json('ageDays')
            kmc_docs = _load_local_json('kmcSessions')
            obs_docs = _load_local_json('observations')
            discharge_docs = _load_local_json('discharges')
            
            # Reconstruct
            reconstructed_babies = _reconstruct_baby_structure(baby_docs, age_days_docs, kmc_docs, obs_docs, lr_docs)
            
            # Add lrBabies as their own entries if needed
            for lr in lr_docs:
                lr['source'] = 'lrBabies'
                reconstructed_babies.append(lr)
                
            # Filter by date/hospital (Simple client-side filtering logic for fake data)
            start_ts = datetime.combine(start_date, datetime.min.time()).timestamp()
            end_ts = datetime.combine(end_date, datetime.max.time()).timestamp()
            
            filtered_babies = []
            for b in reconstructed_babies:
                # Filter by Date (birthDate)
                b_date = b.get('birthDate') or b.get('dateOfBirth')
                if b_date:
                     if not (start_ts <= b_date <= end_ts):
                         continue
                
                # Filter by Hospital
                if hospital_names:
                    h_name = b.get('hospitalName')
                    if h_name not in hospital_names:
                        continue
                
                # Filter by UID
                if uid: 
                    if b.get('UID') != uid:
                        continue
                        
                filtered_babies.append(b)

            # Filter discharges
            filtered_discharges = []
            for d in discharge_docs:
                d_date = d.get('dischargeDate')
                if d_date:
                     if not (start_ts <= d_date <= end_ts):
                         continue
                if uid and d.get('UID') != uid: continue
                
                filtered_discharges.append(d)

            st.session_state['last_query_duration'] = time.time() - start_time
            return filtered_babies, filtered_discharges
            
        except Exception as e:
            st.error(f"Failed to load fake data: {e}")
            return [], []
            
    # --- FIRESTORE MODE ---
    try:
        db = initialize_firebase()
        if not db:
            return [], []

        # Convert dates to Unix timestamps (seconds)
        start_ts = datetime.combine(start_date, datetime.min.time()).timestamp()
        end_ts = datetime.combine(end_date, datetime.max.time()).timestamp()

        # st.info(f"🔍 Querying Firebase for birthDate between {start_date} and {end_date}")

        # 1. Query 'babies' (Master list)
        baby_ref = db.collection('babies')
        baby_query = baby_ref.where(filter=FieldFilter('birthDate', '>=', start_ts)).where(filter=FieldFilter('birthDate', '<=', end_ts))
        
        if uid:
            baby_query = baby_query.where(filter=FieldFilter('UID', '==', uid))
        
        if hospital_names and len(hospital_names) <= 30:
            baby_query = baby_query.where(filter=FieldFilter('hospitalName', 'in', hospital_names))

        baby_docs = load_query_with_retry(baby_query, "babies data")
        
        # 2. Query 'lrBabies' (Supplementary)
        lr_ref = db.collection('lrBabies')
        lr_query = lr_ref.where(filter=FieldFilter('dateOfBirth', '>=', start_ts)).where(filter=FieldFilter('dateOfBirth', '<=', end_ts))
        
        if hospital_names and len(hospital_names) <= 30:
            lr_query = lr_query.where(filter=FieldFilter('hospitalName', 'in', hospital_names))
            
        lr_docs = load_query_with_retry(lr_query, "lrBabies data")

        # 3. Query 'ageDays', 'kmcSessions', 'observations'
        ad_ref = db.collection('ageDays')
        ad_query = ad_ref.where(filter=FieldFilter('ageDayDate', '>=', start_ts)).where(filter=FieldFilter('ageDayDate', '<=', end_ts))
        age_days_docs = load_query_with_retry(ad_query, "ageDays data")
        
        kmc_ref = db.collection('kmcSessions')
        kmc_query = kmc_ref.where(filter=FieldFilter('kmcStart', '>=', start_ts)).where(filter=FieldFilter('kmcStart', '<=', end_ts))
        kmc_docs = load_query_with_retry(kmc_query, "kmcSessions data")
        
        obs_ref = db.collection('observations')
        obs_query = obs_ref.where(filter=FieldFilter('observationCompletedDate', '>=', start_ts)).where(filter=FieldFilter('observationCompletedDate', '<=', end_ts))
        obs_docs = load_query_with_retry(obs_query, "observations data")

        # 4. Query 'discharges'
        discharge_ref = db.collection('discharges')
        discharge_query = discharge_ref.where(filter=FieldFilter('dischargeDate', '>=', start_ts)).where(filter=FieldFilter('dischargeDate', '<=', end_ts))
        if uid:
            discharge_query = discharge_query.where(filter=FieldFilter('UID', '==', uid))
        discharge_docs = load_query_with_retry(discharge_query, "discharge data")

        # Record query duration
        end_time = time.time()
        st.session_state['last_query_duration'] = end_time - start_time

        # RECONSTRUCT STRUCTURE
        reconstructed_babies = _reconstruct_baby_structure(baby_docs, age_days_docs, kmc_docs, obs_docs, lr_docs)
        
        # Add lrBabies as their own entries
        # NOTE: Commented out - only showing main 'babies' collection for now
        # for lr in lr_docs:
        #     lr['source'] = 'lrBabies'
        #     reconstructed_babies.append(lr)

        # Filter discharge data by hospital if specified
        if hospital_names:
            selected_baby_uids = {baby.get('UID') for baby in reconstructed_babies if baby.get('UID')}
            filtered_discharge_data = [d for d in discharge_docs if d.get('UID') in selected_baby_uids]
            discharge_docs = filtered_discharge_data

        return reconstructed_babies, discharge_docs

    except Exception as e:
        st.error(f"Failed to load filtered data: {str(e)}")
        import traceback
        traceback.print_exc()
        return [], []


@st.cache_data(show_spinner="Loading filtered data from Firebase...", ttl=900, max_entries=20)
def load_filtered_followup_data(start_date, end_date, uid=None, hospital_names=None):
    """Load follow-up data filtered by date range - Updated for new schema"""
    
    # --- FAKE DATA MODE ---
    if USE_FAKE_DATA:
        try:
            followups = _load_local_json('followUps')
            
            start_ts = datetime.combine(start_date, datetime.min.time()).timestamp()
            end_ts = datetime.combine(end_date, datetime.max.time()).timestamp()
            
            filtered = []
            for f in followups:
                # Filter by Date
                f_date = f.get('followUpDueDate')
                if f_date:
                    if not (start_ts <= f_date <= end_ts):
                        continue
                        
                # Filter by Hospital
                if hospital_names and f.get('hospitalName') not in hospital_names:
                    continue
                    
                # Filter by UID
                if uid and f.get('UID') != uid:
                    continue
                    
                filtered.append(f)
            return filtered
        except Exception:
            return []

    # --- FIRESTORE MODE ---
    try:
        db = initialize_firebase()
        if not db: return []

        start_ts = datetime.combine(start_date, datetime.min.time()).timestamp()
        end_ts = datetime.combine(end_date, datetime.max.time()).timestamp()

        try:
            followup_ref = db.collection('followUps')
            followup_query = followup_ref.where(filter=FieldFilter('followUpDueDate', '>=', start_ts)).where(filter=FieldFilter('followUpDueDate', '<=', end_ts))

            if uid:
                followup_query = followup_query.where(filter=FieldFilter('UID', '==', uid))

            if hospital_names and len(hospital_names) <= 30:
                followup_query = followup_query.where(filter=FieldFilter('hospitalName', 'in', hospital_names))

            followup_docs = load_query_with_retry(followup_query, "followUps data")
            return followup_docs

        except Exception:
            return []

    except Exception:
        return []


def load_firebase_data(start_date=None, end_date=None, uid=None, hospital_names=None):
    """Load data from Firebase using the new filtered logic"""
    if start_date and end_date:
        return load_filtered_data_from_firebase(start_date, end_date, uid, hospital_names) + (load_filtered_followup_data(start_date, end_date, uid, hospital_names),)
    return [], [], []


def get_db_counts():
    """Get total document counts from Firebase metadata (fast)"""
    try:
        db = initialize_firebase()
        if not db: return None
        
        # Run parallel count queries
        baby_count = db.collection('baby').count().get()[0][0].value
        backup_count = db.collection('babyBackUp').count().get()[0][0].value
        
        return baby_count + backup_count
    except:
        return None

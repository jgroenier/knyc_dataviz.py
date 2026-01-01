#!/usr/bin/env python3
import xarray as xr
import requests
import datetime
import pytz
import os
import tempfile
import sys
import time
import warnings
import numpy as np
import threading
import select

STATION_NAME = "Central Park, NY (KNYC)"
LAT, LON = 40.78, -73.97

FILTER_HRRR_2D  = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl"
FILTER_HRRR_SUB = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_sub.pl"
FILTER_NAM      = "https://nomads.ncep.noaa.gov/cgi-bin/filter_nam_conusnest.pl"

REFRESH_INTERVAL = 180 

HEADERS = {
    'User-Agent': 'Hybrid_Fetcher/11.0 (shiatsu.clunky-3t@icloud.com)',
    'From': 'shiatsu.clunky-3t@icloud.com',
    'Accept': '*/*'
}

C_CYAN  = "\033[96m"
C_RED   = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW= "\033[93m"
C_WHITE = "\033[0m"
C_RESET = "\033[0m"

warnings.filterwarnings("ignore")

class SharedState:
    display_mode = "HRRR" 
    toggle_expire = 0  
    
    nam_data = {}          
    nam_run_label = "Init"
    
    hrrr_hourly = {} 
    hrrr_sub = {}
    hrrr_run_lbl = "Init"
    hrrr_sub_lbl = "Init"
    
state = SharedState()

def download_and_extract(filter_url, params, retry_count=3):
    """
    Downloads GRIB2 using proven v2 logic with min/max validation.
    """
    query = "&".join([f"{k}={v}" for k,v in params.items()])
    url = f"{filter_url}?{query}"
    
    tmp_path = None
    data_points = []
    
    attempts = 0
    while attempts <= retry_count:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            
            if r.status_code == 404: return [], 404
            if r.status_code != 200:
                attempts += 1; time.sleep(1); continue

            with tempfile.NamedTemporaryFile(delete=False, suffix='.grib2') as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name
                
            try:
                ds = xr.open_dataset(tmp_path, engine='cfgrib', backend_kwargs={'indexpath': ''})
                
                target_var = None
                for v in ['t2m', 't', '2t', 'TMP']:
                    if v in ds: target_var = ds[v]; break
                
                if target_var is None:
                    for v in ds.data_vars:
                        try:
                            if 200 < ds[v].min() < 330:
                                target_var = ds[v]
                                break
                        except: continue

                if target_var is not None:
                    vals = np.atleast_1d(target_var.values)
                    
                    if 'valid_time' in ds: times = np.atleast_1d(ds.valid_time.values)
                    elif 'time' in ds: times = np.atleast_1d(ds.time.values)
                    else: times = [datetime.datetime.now()]
                    
                    if vals.ndim > 1: spatial_avg = vals.mean(axis=tuple(range(1, vals.ndim)))
                    else: spatial_avg = vals
                    
                    spatial_avg = np.atleast_1d(spatial_avg)
                    
                    for i in range(min(len(spatial_avg), len(times))):
                        ts_raw = times[i].astype('datetime64[s]').astype(int)
                        ts = datetime.datetime.fromtimestamp(ts_raw, pytz.utc)
                        val_f = (float(spatial_avg[i]) - 273.15) * 1.8 + 32.0
                        data_points.append({'time': ts, 'val_f': val_f})
                
                ds.close()
                return data_points, 200
            except: 
                attempts += 1; time.sleep(1); continue
        except: 
            attempts += 1; time.sleep(1)
        finally:
            if tmp_path and os.path.exists(tmp_path): os.remove(tmp_path)
            
    return [], 500

def fetch_hrrr_run(date_str, hour_str, is_sub=False):
    data_map = {}
    base_url = FILTER_HRRR_SUB if is_sub else FILTER_HRRR_2D
    file_pfx = "wrfsubhf" if is_sub else "wrfsfcf"
    start_f = 1 if is_sub else 0
    
    consecutive_404s = 0
    files_found = 0
    
    for f in range(start_f, 19):
        if consecutive_404s >= 4: break
        f_str = f"{f:02d}"
        params = {
            'file': f"hrrr.t{hour_str}z.{file_pfx}{f_str}.grib2",
            'var_TMP': 'on', 'lev_2_m_above_ground': 'on', 'subregion': 'on',
            'leftlon': str(LON-0.03), 'rightlon': str(LON+0.03),
            'toplat': str(LAT+0.03), 'bottomlat': str(LAT-0.03),
            'dir': f"/hrrr.{date_str}/conus"
        }
        pts, status = download_and_extract(base_url, params)
        if status == 200:
            consecutive_404s = 0; files_found += 1
            for p in pts: data_map[p['time']] = p['val_f']
        elif status == 404: consecutive_404s += 1
        time.sleep(0.02)
    return data_map, files_found

def background_nam_worker():
    while True:
        try:
            now = datetime.datetime.now(pytz.utc)
            found = False
            for lookback in [0, 1, 2, 3]:
                dt = now - datetime.timedelta(hours=lookback*6)
                hr = int(dt.hour / 6) * 6
                run_hour = f"{hr:02d}"
                run_date = dt.strftime('%Y%m%d')
                
                temp_map = {}
                miss_count = 0
                for f in range(0, 48): 
                    if miss_count > 3: break
                    f_str = f"{f:02d}"
                    params = {
                        'file': f"nam.t{run_hour}z.conusnest.hiresf{f_str}.tm00.grib2",
                        'var_TMP': 'on', 'lev_2_m_above_ground': 'on', 'subregion': 'on',
                        'leftlon': str(LON-0.03), 'rightlon': str(LON+0.03),
                        'toplat': str(LAT+0.03), 'bottomlat': str(LAT-0.03),
                        'dir': f"/nam.{run_date}"
                    }
                    pts, status = download_and_extract(FILTER_NAM, params)
                    if status == 200:
                        for p in pts: temp_map[p['time']] = p['val_f']
                    else: miss_count += 1
                    time.sleep(0.05)
                
                if len(temp_map) >= 36:
                    state.nam_data = temp_map
                    state.nam_run_label = f"{run_date} {run_hour}Z"
                    found = True
                    break
            
            if not found: state.nam_run_label = "Searching (>36h)..."

        except Exception: pass
        time.sleep(300)

def run_monitor():
    threading.Thread(target=background_nam_worker, daemon=True).start()
    
    last_refresh_time = 0
    next_data_fetch = 0
    
    while True:
        current_time = time.time()
        
        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            if state.display_mode == "HRRR":
                state.display_mode = "NAM"
                state.toggle_expire = current_time + 60
            else:
                state.display_mode = "HRRR"
                state.toggle_expire = 0
            last_refresh_time = 0

        if state.display_mode == "NAM" and state.toggle_expire > 0:
            if current_time >= state.toggle_expire:
                state.display_mode = "HRRR"
                state.toggle_expire = 0
                last_refresh_time = 0

        if current_time >= next_data_fetch:
            sys.stdout.write(f"\r{C_CYAN}  [SYNC] Downloading latest HRRR data...{C_RESET}")
            sys.stdout.flush()
            
            now_utc = datetime.datetime.now(pytz.utc)
            curr_date = now_utc.strftime('%Y%m%d')
            curr_hour = now_utc.strftime('%H')

            h_map = {}
            s_map = {}
            h_run = "Init"
            h_sub = "Init"
            
            found_b = False
            for lb in [1, 2, 3]:
                b_dt = now_utc - datetime.timedelta(hours=lb)
                bh, bh_cnt = fetch_hrrr_run(b_dt.strftime('%Y%m%d'), b_dt.strftime('%H'), False)
                if bh_cnt >= 12:
                    bs, bs_cnt = fetch_hrrr_run(b_dt.strftime('%Y%m%d'), b_dt.strftime('%H'), True)
                    clr = C_RED if lb >= 2 else C_WHITE
                    for t,v in bh.items(): h_map[t] = (v, clr)
                    for t,v in bs.items(): s_map[t] = (v, clr)
                    h_run = f"Base: {b_dt.strftime('%H')}Z"
                    found_b = True
                    break
            
            if not found_b: h_run = "Base: None"

            lh, lh_cnt = fetch_hrrr_run(curr_date, curr_hour, False)
            ls, ls_cnt = fetch_hrrr_run(curr_date, curr_hour, True)
            if lh_cnt > 0 or ls_cnt > 0:
                h_sub = f"Live: {curr_hour}Z"
                for t,v in lh.items(): h_map[t] = (v, C_CYAN)
                for t,v in ls.items(): s_map[t] = (v, C_CYAN)
            else:
                h_sub = f"Waiting {curr_hour}Z"

            state.hrrr_hourly = h_map
            state.hrrr_sub = s_map
            state.hrrr_run_lbl = h_run
            state.hrrr_sub_lbl = h_sub
            
            next_data_fetch = current_time + REFRESH_INTERVAL
            last_refresh_time = 0 

        if current_time - last_refresh_time >= 1.0 or last_refresh_time == 0:
            os.system('cls' if os.name == 'nt' else 'clear')
            et = pytz.timezone('US/Eastern')
            
            hrrr_map = state.hrrr_hourly
            sub_map = state.hrrr_sub
            
            mode_str = f"{C_CYAN}HRRR (Primary){C_RESET}" if state.display_mode == "HRRR" else f"{C_GREEN}NAM NEST (Overlay){C_RESET}"
            print(f"=======================================================================================")
            print(f"  HYBRID MONITOR | {STATION_NAME} | Mode: {mode_str}")
            print(f"=======================================================================================")
            
            display_map = {}
            if state.display_mode == "NAM":
                rem = int(state.toggle_expire - current_time)
                print(f"  Source: {state.nam_run_label}")
                print(f"  {C_GREEN}>> AUTO-REVERT IN: {rem:02d}s <<{C_RESET}  (Press ENTER to cancel)")
                for t, v in state.nam_data.items(): display_map[t] = (v, C_GREEN)
            else:
                print(f"  Status: {state.hrrr_run_lbl} | {state.hrrr_sub_lbl}")
                print(f"  Debug:  Sub-Hourly Pts: {len(sub_map)}")
                print(f"  Legend: {C_RED}Red{C_RESET}=Stale (>2h)  {C_WHITE}White{C_RESET}=Backup  {C_CYAN}Cyan{C_RESET}=Fresh")
                display_map = hrrr_map

            print(f"---------------------------------------------------------------------------------------")
            print(f"  {'TIME (ET)':<20} | {'TEMP':<8} | {'SUB-HOURLY INTERLACE':<32} | {'TREND / MAX'}")
            print(f"  {'-'*20} | {'-'*8} | {'-'*32} | {'-'*20}")

            sorted_times = sorted(display_map.keys())
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            
            if display_map:
                vals = [x[0] for x in display_map.values()]
                min_v, max_v = min(vals), max(vals)
                peak_val = max_v
            else:
                min_v, max_v, peak_val = 0, 100, 0

            for t in sorted_times:
                if t < cutoff: continue
                local_t = t.astimezone(et)
                val, color = display_map[t]
                
                subs_str = ""
                if state.display_mode == "HRRR":
                    sub_parts = []
                    for m in [15, 30, 45]:
                        target = t + datetime.timedelta(minutes=m)
                        match = None
                        for k, v in sub_map.items():
                            if abs((k - target).total_seconds()) < 90:
                                match = v; break
                        if match:
                            sv, sc = match
                            sub_parts.append(f"{sc}:{m} {sv:.1f}°{C_RESET}") 
                        else:
                            sub_parts.append("          ")
                    subs_str = " ".join(sub_parts)
                else:
                    subs_str = f"{C_WHITE}[Hourly Only]{C_RESET}"

                range_v = max_v - min_v if max_v > min_v else 1
                bar_len = int(((val - min_v) / range_v) * 15)
                bar = "|" * bar_len
                marker = " < MAX" if val >= peak_val - 0.1 else ""
                bar_clr = C_RED if marker else C_YELLOW
                
                print(f"  {local_t.strftime('%a %I %p'):<20} | {color}{val:.2f}°{C_RESET}   | {subs_str:<32} | {bar_clr}{bar}{C_RESET}{marker}")
            
            print(f"---------------------------------------------------------------------------------------")
            next_r_dt = datetime.datetime.fromtimestamp(next_data_fetch)
            print(f"  Next Refresh: {next_r_dt.strftime('%I:%M:%S %p')} (Press ENTER to toggle)")
            
            last_refresh_time = current_time

        time.sleep(0.1)

if __name__ == "__main__":
    try:
        run_monitor()
    except KeyboardInterrupt:
        sys.exit(0)
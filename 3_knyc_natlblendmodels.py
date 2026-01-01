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

STATION_NAME = "Central Park, NY (KNYC)"
LAT, LON = 40.78, -73.97

FILTER_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_blend.pl"

REFRESH_INTERVAL = 600

HEADERS = {
    'User-Agent': 'NBM_Fetcher/3.0 (shiatsu.clunky-3t@icloud.com)',
    'From': 'shiatsu.clunky-3t@icloud.com',
    'Accept': '*/*'
}

C_CYAN  = "\033[96m"
C_RED   = "\033[91m"
C_YELLOW= "\033[93m"
C_WHITE = "\033[0m"
C_RESET = "\033[0m"

warnings.filterwarnings("ignore")

def download_and_extract(filter_url, params, retry_count=2):
    """
    Downloads Micro-Crop GRIB with Aggressive Retry.
    """
    query = "&".join([f"{k}={v}" for k,v in params.items()])
    url = f"{filter_url}?{query}"
    
    attempts = 0
    while attempts <= retry_count:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 404: return [], 404
            if r.status_code != 200:
                attempts += 1; time.sleep(1); continue

            with tempfile.NamedTemporaryFile(delete=False, suffix='.grib2') as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name
                
            try:
                ds = xr.open_dataset(tmp_path, engine='cfgrib', backend_kwargs={'indexpath': ''})
                target_var = None
                for v in ['t2m', 't', 'TMP', '2t']:
                    if v in ds: target_var = ds[v]; break
                
                points = []
                if target_var is not None:
                    vals = np.atleast_1d(target_var.values)
                    if 'valid_time' in ds: times = np.atleast_1d(ds.valid_time.values)
                    elif 'time' in ds: times = np.atleast_1d(ds.time.values)
                    else: times = [datetime.datetime.now()]
                    
                    if vals.ndim > 1: spatial_avg = vals.mean(axis=tuple(range(1, vals.ndim)))
                    else: spatial_avg = vals
                    
                    spatial_avg = np.atleast_1d(spatial_avg)
                    for i in range(min(len(spatial_avg), len(times))):
                        ts = datetime.datetime.fromtimestamp(times[i].astype('datetime64[s]').astype(int), pytz.utc)
                        val_f = (float(spatial_avg[i]) - 273.15) * 1.8 + 32.0
                        points.append({'time': ts, 'val_f': val_f})
                ds.close()
                return points, 200
            except Exception: 
                attempts += 1; time.sleep(1); continue
        except: 
            attempts += 1; time.sleep(1)
        finally:
            if 'tmp_path' in locals() and tmp_path and os.path.exists(tmp_path): os.remove(tmp_path)
            
    return [], 500

def fetch_nbm_run(date_str, hour_str):
    """
    Fetches NBM Hourly Core for F001 - F036.
    """
    data_map = {}
    consecutive_404s = 0
    files_found = 0
    gap_tolerance = 2 
    
    print(f"     -> Scraper starting for {date_str} {hour_str}Z...")

    for f in range(1, 37):
        if consecutive_404s >= gap_tolerance: break
        f_str = f"{f:03d}" 
        
        params = {
            'file': f"blend.t{hour_str}z.core.f{f_str}.co.grib2",
            'var_TMP': 'on', 'lev_2_m_above_ground': 'on', 'subregion': 'on',
            'leftlon': str(LON-0.03), 'rightlon': str(LON+0.03),
            'toplat': str(LAT+0.03), 'bottomlat': str(LAT-0.03),
            'dir': f"/blend.{date_str}/{hour_str}/core"
        }
        
        pts, status = download_and_extract(FILTER_URL, params)
        
        if status == 200:
            consecutive_404s = 0; files_found += 1
            sys.stdout.write(f"\r     -> Fetched F{f_str} | Found: {files_found}/36")
            sys.stdout.flush()
            for p in pts: data_map[p['time']] = p['val_f']
        elif status == 404:
            consecutive_404s += 1
            sys.stdout.write(f"\r     -> Missing F{f_str} (404)...")
            sys.stdout.flush()
        elif status == 500:
            sys.stdout.write(f"\r     -> Error F{f_str} (Retrying)...")
            sys.stdout.flush()
        time.sleep(0.05) 
        
    print("") 
    return data_map, files_found

def run_monitor():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("==========================================================================")
        print("  NBM (NATIONAL BLEND) 36HR TEMP MONITOR")
        print(f"  Target: {STATION_NAME} | Source: NOMADS")
        print("==========================================================================")
        
        now_utc = datetime.datetime.now(pytz.utc)
        
        master_data = {}
        run_label = "Waiting..."
        run_found = False
        run_color = C_WHITE
        
        for lookback in range(0, 7):
            check_dt = now_utc - datetime.timedelta(hours=lookback)
            check_date = check_dt.strftime('%Y%m%d')
            check_hour = check_dt.strftime('%H')
            
            print(f"  Checking Run: {check_hour}Z (Age: {lookback}h)...")
            data, count = fetch_nbm_run(check_date, check_hour)
            
            if count == 36: 
                master_data = data
                run_label = f"{check_hour}Z (Age: {lookback}h)"
                run_found = True
                
                if lookback == 0:
                    run_color = C_CYAN
                elif lookback == 1:
                    run_color = C_WHITE
                else:
                    run_color = C_RED
                
                print(f"     -> {run_color}SECURED COMPLETE RUN ({count}/36 files){C_RESET}")
                break
            else:
                print(f"     -> Incomplete ({count}/36). Trying older...")

        if not run_found:
            print(f"  {C_RED}[CRITICAL]{C_RESET} Could not find a COMPLETE (36h) NBM run in last 6 hours.")
            print("             NOMADS may be delayed or the filter URL has changed.")

        os.system('cls' if os.name == 'nt' else 'clear')
        et = pytz.timezone('US/Eastern')
        
        print(f"========================================================================")
        print(f"  NBM FORECAST (Next 36h Hourly) | {STATION_NAME}")
        print(f"  Run: {run_label}")
        print(f"  Legend: {C_RED}Red{C_RESET}=Stale (>2h)  {C_WHITE}White{C_RESET}=Recent (1h)  {C_CYAN}Cyan{C_RESET}=Live")
        print(f"========================================================================")
        print(f"  {'TIME (ET)':<20} | {'TEMP (F)':<10} | {'TREND / MAX'}")
        print(f"  {'-'*20} | {'-'*10} | {'-'*30}")

        sorted_times = sorted(master_data.keys())
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)

        if master_data:
            vals = list(master_data.values())
            min_v = min(vals)
            max_v = max(vals)
            
            peak_val = -999
            for t in sorted_times:
                if master_data[t] > peak_val: peak_val = master_data[t]

            for t in sorted_times:
                if t < cutoff: continue
                
                local_t = t.astimezone(et)
                val = master_data[t]
                
                range_v = max_v - min_v
                if range_v == 0: range_v = 1
                
                bar_len = int(((val - min_v) / range_v) * 20)
                bar = "|" * bar_len
                
                color = run_color 
                bar_color = C_YELLOW
                marker = ""
                
                if val >= peak_val - 0.1:
                    bar_color = C_RED
                    marker = f" <--- MAX ({val:.1f}°)"
                
                print(f"  {local_t.strftime('%a %I %p'):<20} | {color}{val:.2f}°{C_RESET}     | {bar_color}{bar}{C_RESET}{marker}")

        else:
            print("\n  [NO DATA] Waiting for complete NBM run to populate...")

        print(f"------------------------------------------------------------------------")
        next_r = datetime.datetime.now() + datetime.timedelta(seconds=REFRESH_INTERVAL)
        print(f"  Next Refresh: {next_r.strftime('%I:%M:%S %p')}")
        
        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    try:
        run_monitor()
    except KeyboardInterrupt:
        sys.exit(0)
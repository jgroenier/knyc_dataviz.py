#!/usr/bin/env python3
import time
import sys
import os
import math
import threading
import requests
import select
import re
from datetime import datetime, timezone, timedelta

KEEP_BUOYS = ["44065", "44025", "44091", "SDHN4"]

RAW_STATIONS = {
    "KPIT": {"lat": 40.49, "lon": -80.23}, 
    "KALB": {"lat": 42.75, "lon": -73.80}, 
    "KBWI": {"lat": 39.17, "lon": -76.67}, 

    "44065": {"lat": 40.369, "lon": -73.703, "type": "buoy"},
    "44025": {"lat": 40.251, "lon": -73.164, "type": "buoy"},
    "44091": {"lat": 39.770, "lon": -73.600, "type": "buoy"},
    "SDHN4": {"lat": 40.467, "lon": -74.009, "type": "buoy"},

    "KEWR": {"lat": 40.67, "lon": -74.24}, 
    "KTEB": {"lat": 40.92, "lon": -74.06}, 
    "KLGA": {"lat": 40.77, "lon": -73.82}, 
    "KJFK": {"lat": 40.60, "lon": -73.74}, 
    "KCDW": {"lat": 40.90, "lon": -74.32}, 
    "KLDJ": {"lat": 40.55, "lon": -74.27}, 
    "KMMU": {"lat": 40.79, "lon": -74.45}, 
    "KSMQ": {"lat": 40.62, "lon": -74.67}, 
    "KBLM": {"lat": 40.18, "lon": -74.05}, 

    "KFRG": {"lat": 40.73, "lon": -73.41},
    "KISP": {"lat": 40.79, "lon": -73.10}, 
    "KHWV": {"lat": 40.82, "lon": -72.86}, 
    "KFOK": {"lat": 40.85, "lon": -72.63}, 
    "KHTO": {"lat": 40.96, "lon": -72.25}, 
    "KMTP": {"lat": 41.07, "lon": -71.92}, 

    "KHPN": {"lat": 41.07, "lon": -73.71}, 
    "KSWF": {"lat": 41.50, "lon": -74.10}, 
    "KPOU": {"lat": 41.62, "lon": -73.88}, 
    "KMGJ": {"lat": 41.51, "lon": -74.26}, 
    "KMSV": {"lat": 41.70, "lon": -74.79},
    "KDXR": {"lat": 41.37, "lon": -73.48}, 
    "KBDR": {"lat": 41.16, "lon": -73.13}, 
    "KHVN": {"lat": 41.26, "lon": -72.88}, 
    "KFWN": {"lat": 41.20, "lon": -74.62},
    "KBDL": {"lat": 41.93, "lon": -72.68}, 
    "KGON": {"lat": 41.33, "lon": -72.05}, 
    "KOXC": {"lat": 41.48, "lon": -73.13}, 
    "KPSF": {"lat": 42.43, "lon": -73.29}, 
    "KBAF": {"lat": 42.16, "lon": -72.71}, 

    "KTTN": {"lat": 40.28, "lon": -74.81},
    "KWRI": {"lat": 40.01, "lon": -74.59}, 
    "KNEL": {"lat": 40.03, "lon": -74.35}, 
    "KVAY": {"lat": 39.94, "lon": -74.84}, 
    "KMIV": {"lat": 39.36, "lon": -75.07}, 
    "KACY": {"lat": 39.45, "lon": -74.57},
    "KMJX": {"lat": 39.93, "lon": -74.29}, 
    "KOBI": {"lat": 39.21, "lon": -74.80}, 
    
    "KPHL": {"lat": 39.87, "lon": -75.24}, 
    "KPNE": {"lat": 40.08, "lon": -75.01}, 
    "KLOM": {"lat": 40.14, "lon": -75.26}, 
    "KDYL": {"lat": 40.33, "lon": -75.12}, 
    "KUKT": {"lat": 40.43, "lon": -75.38}, 
    "KABE": {"lat": 40.65, "lon": -75.44}, 
    "KMPO": {"lat": 41.13, "lon": -75.38}, 
    "KRDG": {"lat": 40.37, "lon": -75.96}, 
    "KLNS": {"lat": 40.12, "lon": -76.29}, 
    "KXLL": {"lat": 40.57, "lon": -75.49}, 
    "KCKZ": {"lat": 40.40, "lon": -75.30}, 
    "KPTW": {"lat": 40.24, "lon": -75.56}, 
    "KMQS": {"lat": 39.98, "lon": -75.87},
    "KBGM": {"lat": 42.21, "lon": -75.98}, 
    "KAVP": {"lat": 41.34, "lon": -75.73},
    "KIPT": {"lat": 41.24, "lon": -76.92}, 
    "KUNV": {"lat": 40.85, "lon": -77.85},
    "KELM": {"lat": 42.16, "lon": -76.89}, 
    "KITH": {"lat": 42.49, "lon": -76.46}, 
    "KBFD": {"lat": 41.80, "lon": -78.64}, 
    
    "KJST": {"lat": 40.32, "lon": -78.83}, 
    "KAOO": {"lat": 40.30, "lon": -78.32}, 
    "KAGC": {"lat": 40.35, "lon": -79.93}, 
    "KLBE": {"lat": 40.28, "lon": -79.41},
    "KDUJ": {"lat": 41.18, "lon": -78.90}, 
    "KIDI": {"lat": 40.63, "lon": -79.10}, 
    "KILG": {"lat": 39.68, "lon": -75.61}, 
    "KMRB": {"lat": 39.40, "lon": -77.98}, 
    "KCBE": {"lat": 39.62, "lon": -78.76}, 
    "KTHV": {"lat": 39.92, "lon": -76.87}, 
}

STATION_DB = {
    k: v for k, v in RAW_STATIONS.items() 
    if (not any(c.isdigit() for c in k) or k in KEEP_BUOYS)
    and v['lat'] >= 39.17 and v['lon'] >= -80.23
}

CENTER_LAT, CENTER_LON = 40.78, -73.97
LAT_MIN, LAT_MAX = 39.17, 42.75
LON_MIN, LON_MAX = -80.23, -71.50 

MAP_WIDTH, MAP_HEIGHT = 90, 30
API_DELAY = 3.0 
HEADERS = {'User-Agent': '(WeatherVizTesting, expert-gyro-1x@icloud.com)', 'Accept': 'application/geo+json'}

def c_to_f(c): 
    if c is None: return None
    try: return (float(c) * 9/5) + 32
    except: return None

def get_wind_mph(val, unit):
    if val is None: return None
    try:
        v = float(val)
        u = str(unit).lower()
  
        if 'km_h' in u or 'km/h' in u: return v * 0.621371
        return v * 2.23694 
    except: return None

def parse_raw_wind(raw_msg):
    if not raw_msg: return None
    try:
        match = re.search(r'\b(?:VRB|\d{3})(\d{2,3})(?:G\d{2,3})?(KT|MPS|KMH)\b', raw_msg)
        if match:
            speed = float(match.group(1))
            unit = match.group(2)
    
            if unit == 'KT': return speed * 0.514444
            elif unit == 'KMH': return speed * 0.277778
            else: return speed
    except: pass
    return None

def m_to_mi(m): 
    if m is None: return None
    try: return float(m) * 0.000621371
    except: return None

def pa_to_inHg(p): 
    if p is None: return None
    try: return float(p) * 0.0002953
    except: return None

def deg_to_cardinal(d):
    if d is None: return None
    try:
        val = float(d)
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        ix = int((val + 11.25)/22.5)
        return dirs[ix % 16]
    except: return None

def parse_iso_time(ts_str):
    if not ts_str: return None
    try:
        clean = ts_str.replace('Z', '+00:00')
     
        if 'T' in clean and '+' not in clean and '-' not in clean[-6:]:
             clean += '+00:00'
        return datetime.fromisoformat(clean)
    except:
        return None

def calc_rh(t_c, dp_c):
    if t_c is None or dp_c is None: return None
    try:
        a = 17.625
        b = 243.04
        
        num = math.exp((a * dp_c) / (b + dp_c))
        den = math.exp((a * t_c) / (b + t_c))
        return 100.0 * (num / den)
    except: return None

def get_age_stats(timestamp_str):
    ts = parse_iso_time(timestamp_str)
    FRESH_COLOR = "\033[92m" 
    
    if not ts: return "\033[90m", True, datetime.min.replace(tzinfo=timezone.utc), False
    
    diff = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    is_fresh = (diff <= 20)
    
    if diff > 120: return "\033[90m", True, ts, False   
    if diff > 60:  return "\033[91m", False, ts, False  
    if diff > 20:  return "\033[93m", False, ts, False  
    
    return FRESH_COLOR, False, ts, True 

def is_valid_data(props):
    if not props: return False
    has_temp = props.get('temperature', {}).get('value') is not None
    has_wind = props.get('windSpeed', {}).get('value') is not None
    return has_temp or has_wind

def parse_tgftp_metar(raw_text, sid):
    if not raw_text or len(raw_text) < 10: return None
    try:
        now = datetime.now(timezone.utc)
        ts_match = re.search(r'\b(\d{2})(\d{4})Z\b', raw_text)
        if ts_match:
            day = int(ts_match.group(1))
            hhmm = ts_match.group(2)
            month = now.month
            year = now.year
            if day > now.day + 1: 
                month -= 1
                if month == 0:
                    month = 12
                    year -= 1
            ts_iso = f"{year:04d}-{month:02d}-{day:02d}T{hhmm[:2]}:{hhmm[2:]}:00+00:00"
        else:
            ts_iso = now.isoformat()

        w_spd, w_dir = None, None
        w_match = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G\d{2,3})?(KT|MPS|KMH)\b', raw_text)
        if w_match:
            d_str = w_match.group(1)
            s_str = w_match.group(2)
            u_str = w_match.group(3)
            w_dir = float(d_str) if d_str != 'VRB' else 0.0
            raw_spd = float(s_str)
            if u_str == 'KT': w_spd = raw_spd * 0.514444
            elif u_str == 'KMH': w_spd = raw_spd * 0.277778
            else: w_spd = raw_spd

        t_val, d_val = None, None
        t_match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', raw_text)
        if t_match:
            def parse_t(s): return -float(s[1:]) if 'M' in s else float(s)
            t_val = parse_t(t_match.group(1))
            d_val = parse_t(t_match.group(2))

        p_val = None
        p_match = re.search(r'\bA(\d{4})\b', raw_text)
        if p_match:
            inhg = float(p_match.group(1)) / 100.0
            p_val = inhg * 3386.39

        rh = calc_rh(t_val, d_val)

        return {
            'timestamp': ts_iso,
            'temperature': {'value': t_val},
            'dewpoint': {'value': d_val},
            'windDirection': {'value': w_dir},
            'windSpeed': {'value': w_spd, 'unitCode': 'unit:m_s-1'},
            'barometricPressure': {'value': p_val},
            'visibility': {'value': None},
            'precipitationLastHour': {'value': None},
            'relativeHumidity': {'value': rh},
            'rawMessage': raw_text.strip()
        }
    except: return None

class StationManager:
    def __init__(self):
        self.stations = {
            sid: {
                'lat': c['lat'], 
                'lon': c['lon'], 
                'type': c.get('type', 'land'), 
                'data': None,
                'history': [] 
            } for sid, c in STATION_DB.items()
        }
        self.fetch_queue = sorted(list(self.stations.keys()))
        self.last_data_change = time.time()
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.session = requests.Session() 

    def background_crawler(self):
        idx = 0
        while not self.stop_event.is_set():
            if not self.fetch_queue:
                time.sleep(1)
                continue
            
            sid = self.fetch_queue[idx % len(self.fetch_queue)]
            self.smart_fetch(sid)
            
            idx += 1
            time.sleep(API_DELAY)

    def smart_fetch(self, sid):
        is_buoy = (sid in KEEP_BUOYS)
        
        if is_buoy:
            res = self.fetch_nws(sid)
            if res: self.update_data(sid, res)
            return

        res_awc = self.fetch_awc(sid)
        
        awc_ok = False
        if is_valid_data(res_awc):
            ts = parse_iso_time(res_awc.get('timestamp'))
            if ts:
                age_mins = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
                if age_mins < 20: awc_ok = True

        res_tg = None
        if not awc_ok:
            res_tg = self.fetch_tgftp(sid)
        
        res_nws = None
        tg_ok = is_valid_data(res_tg)
        if not awc_ok and not tg_ok:
            res_nws = self.fetch_nws(sid)

        winner = self.pick_best_data([res_awc, res_tg, res_nws])
        if winner:
            self.update_data(sid, winner)

    def pick_best_data(self, dataset):
        best = None
        best_ts = datetime.min.replace(tzinfo=timezone.utc)
        for d in dataset:
            if not is_valid_data(d): continue
            ts = parse_iso_time(d.get('timestamp'))
            if ts and ts >= best_ts:
                best_ts = ts
                best = d
        return best

    def fetch_tgftp(self, sid):
        try:
            url = f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{sid}.TXT"
            resp = self.session.get(url, timeout=3)
            if resp.status_code == 200:
                lines = resp.text.strip().split('\n')
                if len(lines) >= 2:
                    return parse_tgftp_metar(lines[1], sid)
        except: pass
        return None

    def fetch_nws(self, sid):
        try:
            url = f"https://api.weather.gov/stations/{sid}/observations?limit=1"
            resp = self.session.get(url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                features = resp.json().get('features', [])
                if features:
                    props = features[0].get('properties', {})
                    if props.get('windSpeed', {}).get('value') is None:
                        raw = props.get('rawMessage', '')
                        spd = parse_raw_wind(raw)
                        if spd is not None:
                            if not props.get('windSpeed'): props['windSpeed'] = {}
                            props['windSpeed']['value'] = spd
                            props['windSpeed']['unitCode'] = 'unit:m_s-1'
                    return props
        except: pass
        return None

    def fetch_awc(self, sid):
        try:
            url = f"https://aviationweather.gov/api/data/metar?ids={sid}&format=json"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    m = data[0]
                    raw_time = m.get('obsTime')
                    if raw_time:
                         if ' ' in raw_time: raw_time = raw_time.replace(' ', 'T')
                         if not raw_time.endswith('Z'): raw_time += 'Z'
                    
                    w_kt = m.get('wspd')
                    w_ms = float(w_kt)*0.514444 if w_kt is not None else None
                    v_m = float(m.get('visib',0))*1609.34 if m.get('visib') else None
                    alt = m.get('altim')
                    p_pa = float(alt)*100.0 if alt is not None else None
                    pr_in = m.get('precip')
                    pr_m = float(pr_in)*0.0254 if pr_in is not None else None
                    t = m.get('temp')
                    dp = m.get('dewp')
                    rh = calc_rh(t, dp)

                    return {
                        'timestamp': raw_time,
                        'temperature': {'value': t},
                        'dewpoint': {'value': dp},
                        'windDirection': {'value': m.get('wdir')},
                        'windSpeed': {'value': w_ms, 'unitCode': 'unit:m_s-1'},
                        'barometricPressure': {'value': p_pa},
                        'visibility': {'value': v_m},
                        'precipitationLastHour': {'value': pr_m},
                        'relativeHumidity': {'value': rh},
                        'rawMessage': m.get('rawOb')
                    }
        except: pass
        return None

    def update_data(self, sid, props):
        with self.lock:
            self.stations[sid]['data'] = props
            ts = parse_iso_time(props.get('timestamp'))
            
            if ts:
                def val(k): return props.get(k, {}).get('value')
                record = {
                    'ts': ts,
                    'temp': val('temperature'),
                    'ws': val('windSpeed'),
                    'ws_u': props.get('windSpeed', {}).get('unitCode', ''),
                    'wd': val('windDirection'),
                    'rh': val('relativeHumidity'),
                    'dew': val('dewpoint'),
                    'precip': val('precipitationLastHour'),
                    'pres': val('barometricPressure'),
                    'vis': val('visibility')
                }
                hist = self.stations[sid]['history']
                if not hist or hist[-1]['ts'] != ts:
                    hist.append(record)
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                    if hist[0]['ts'] < cutoff:
                        self.stations[sid]['history'] = [x for x in hist if x['ts'] > cutoff]
            self.last_data_change = time.time()

class MapUI:
    def __init__(self, manager):
        self.mgr = manager
        self.last_draw_time = 0
        self.mode = "TEMP"
        self.mode_expiry = 0 
        self.input_buffer = ""
        self.last_msg = ""

    def get_grid_pos(self, lat, lon):
        if LAT_MAX == LAT_MIN: return (None, None)
        y_norm = (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)
        row = int((1.0 - y_norm) * (MAP_HEIGHT - 1))
        
        if LON_MAX == LON_MIN: return (None, None)
        x_norm = (lon - LON_MIN) / (LON_MAX - LON_MIN)
        col = int(x_norm * (MAP_WIDTH - 1))
        
        return (row, col) if 0 <= row < MAP_HEIGHT and 0 <= col < MAP_WIDTH else (None, None)

    def get_value_with_lookback(self, sid, key, unit_key=None, max_age_mins=90):
        info = self.mgr.stations.get(sid)
        if not info or not info['history']: return None, None
        
        hist = info['history']
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_mins)
        
        for record in reversed(hist):
            if record['ts'] < cutoff_time: break
            val = record.get(key)
            if val is not None:
                u = record.get(unit_key) if unit_key else None
                return val, u
        return None, None

    def get_trend(self, sid, hours_back):
        info = self.mgr.stations.get(sid)
        if not info or not info['history']: return "?"
        hist = info['history']
        curr_val, curr_ts = None, None
        for rec in reversed(hist):
            if rec['temp'] is not None:
                curr_val = rec['temp']
                curr_ts = rec['ts']
                break
        
        if curr_val is None: return "?"
        target_time = curr_ts - timedelta(hours=hours_back)
        best_val, min_diff = None, 3600
        
        for rec in hist:
            if rec['temp'] is None: continue
            diff = abs((rec['ts'] - target_time).total_seconds())
            if diff < min_diff:
                min_diff = diff
                best_val = rec['temp']
        
        if best_val is None or min_diff > 1800: return "."
        diff_c = float(curr_val) - float(best_val)
        return f"{'+' if diff_c > 0 else ''}{int(diff_c * 9/5)}"

    def get_precip_sum(self, sid, hours_back):
        info = self.mgr.stations.get(sid)
        if not info or not info['history']: return "?"
        hist = info['history']
        curr_ts = hist[-1]['ts']
        start_time = curr_ts - timedelta(hours=hours_back)
        
        hourly_max = {}
        for rec in hist:
            if rec['ts'] <= start_time or rec['ts'] > curr_ts: continue
            p = rec.get('precip')
            if p is not None:
                key = rec['ts'].strftime('%Y%m%d%H')
                if key not in hourly_max or p > hourly_max[key]:
                    hourly_max[key] = p
        
        total_m = sum(hourly_max.values())
        if total_m == 0: return "0"
        return f"{total_m * 39.3701:.2f}"

    def get_label_value(self, sid, props, is_fresh):
        try:
            if self.mode == "TEMP":
                v, _ = self.get_value_with_lookback(sid, 'temp')
                if v is not None:
                    return f"{c_to_f(v):.1f}" if is_fresh else f"{int(c_to_f(v))}"
                return "-"
            elif self.mode == "WS":
                v, u = self.get_value_with_lookback(sid, 'ws', 'ws_u')
                return f"{int(get_wind_mph(v, u))}" if v is not None else "?"
            elif self.mode == "WD":
                v, _ = self.get_value_with_lookback(sid, 'wd')
                return deg_to_cardinal(v) if v is not None else "?"
            elif self.mode == "H": 
                v, _ = self.get_value_with_lookback(sid, 'rh')
                return f"{int(v)}%" if v is not None else "-"
            elif self.mode == "D": 
                v, _ = self.get_value_with_lookback(sid, 'dew')
                return f"{c_to_f(v):.1f}" if v is not None and is_fresh else "-"
            elif self.mode == "P":
                return self.get_precip_sum(sid, 1)
            elif self.mode == "P1": return self.get_precip_sum(sid, 1)
            elif self.mode == "P3": return self.get_precip_sum(sid, 3)
            elif self.mode == "P6": return self.get_precip_sum(sid, 6)
            elif self.mode == "P24": return self.get_precip_sum(sid, 24)
            
            elif self.mode == "T1": return self.get_trend(sid, 1)
            elif self.mode == "T2": return self.get_trend(sid, 2)
            elif self.mode == "T3": return self.get_trend(sid, 3)
            elif self.mode == "T6": return self.get_trend(sid, 6)
            elif self.mode == "T9": return self.get_trend(sid, 9)
            elif self.mode == "T12": return self.get_trend(sid, 12)
            elif self.mode == "T18": return self.get_trend(sid, 18)
            elif self.mode == "T24": return self.get_trend(sid, 24)
            elif self.mode == "PRES":
                v, _ = self.get_value_with_lookback(sid, 'pres')
                return f"{int(pa_to_inHg(v)*100)%100:02d}" if v is not None else "-" 
            elif self.mode == "VIS":
                v, _ = self.get_value_with_lookback(sid, 'vis')
                return f"{int(m_to_mi(v))}" if v is not None else "-"
        except: return "X"
        return "?"

    def is_collision(self, grid, r, c, text):
        if r < 0 or r >= MAP_HEIGHT: return True
        for i in range(len(text)):
            if c + i >= MAP_WIDTH: return True
            if grid[r][c+i] != ' ': 
                return True
        return False

    def find_valid_pos(self, grid, r, c, label_text, val_text, is_buoy):
        if not is_buoy:
            offsets = [
                (0,0), (0,-4), (-1,-4), (1,-4), (0, -8), (-1, 0), (1, 0),
                (2,0), (-2,0), (0,4)
            ]
        else:
            offsets = [
                (0,0), (0,4), (0,8), (1,4), (-1,4), (0,-4), (1,0), (-1,0)
            ]
        
        for dr, dc in offsets:
            nr, nc = r + dr, c + dc
            if nr-1 < 0 or nr >= MAP_HEIGHT or nc < 0 or nc >= MAP_WIDTH: continue
            if self.is_collision(grid, nr-1, nc, label_text): continue
            if self.is_collision(grid, nr, nc, val_text): continue
            return nr, nc
        return None, None 

    def draw(self, prompt=""):
        now = time.time()
        if self.mode != "TEMP" and now > self.mode_expiry:
            self.mode = "TEMP"
            self.last_msg = "Reverted to Standard."
        if prompt: self.last_msg = prompt
        grid = [[' ' for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
        BOLD, CYAN_BLUE, RESET = "\033[1m", "\033[96m", "\033[0m"
        
        with self.mgr.lock:
            render_list = []
            for sid, info in self.mgr.stations.items():
                props = info['data']
                ts_str = props.get('timestamp') if props else None
                age_color, is_stale, dt, is_fresh = get_age_stats(ts_str)
                
                render_list.append({
                    'sid': sid, 'info': info, 'props': props, 
                    'color': age_color, 'stale': is_stale, 
                    'fresh': is_fresh, 'lat': info['lat'], 'lon': info['lon']
                })
            
            render_list.sort(key=lambda x: -x['lat'])

            for item in render_list:
                sid = item['sid']
                info = item['info']
                age_color = item['color']
                
                val_str = self.get_label_value(sid, item['props'], item['fresh'])
                label_txt = f"[{val_str}]" if not item['stale'] else "[-]"
                name_str = sid[-3:]
                
                r, c = self.get_grid_pos(info['lat'], info['lon'])
                
                if r is not None:
                    is_buoy = (sid in KEEP_BUOYS)
                    valid_r, valid_c = self.find_valid_pos(grid, r, c, name_str, label_txt, is_buoy)
                    if valid_r is not None:
                        for i, char in enumerate(name_str):
                            if valid_c + i < MAP_WIDTH:
                                grid[valid_r-1][valid_c+i] = age_color + char + RESET
                        val_color = CYAN_BLUE if is_buoy else RESET 
                        for i, char in enumerate(label_txt):
                            if valid_c + i < MAP_WIDTH:
                                grid[valid_r][valid_c+i] = val_color + char + RESET

            r_nyc, c_nyc = self.get_grid_pos(CENTER_LAT, CENTER_LON)
            if r_nyc is not None and c_nyc is not None:
                if grid[r_nyc][c_nyc] == ' ':
                    grid[r_nyc][c_nyc] = BOLD + "+" + RESET

        os.system('cls' if os.name == 'nt' else 'clear')
        
        time_left = ""
        if self.mode != "TEMP":
            rem = int(self.mode_expiry - now)
            time_left = f" (Revert: {rem}s)"
            
        print(f"┌{'─'*(MAP_WIDTH-2)}┐")
        title = f" [{self.mode}] MAP {time_left}".center(MAP_WIDTH-2)
        print(f"│{title}│")
        print(f"├{'─'*(MAP_WIDTH-2)}┤")
        for row in grid: print("│" + "".join(row) + "│")
        print(f"└{'─'*(MAP_WIDTH-2)}┘")
        
        print(f" Cmds: WS, WD, H, D, P1, P3, P6, P24, T1, T2, T3, T6, T9, T12, T18, T24")
        if self.last_msg: print(f" Result: {self.last_msg}")
        print(f"\ncmd> {self.input_buffer}", end="", flush=True)
        self.last_draw_time = time.time()

    def handle_command(self, cmd):
        parts = cmd.strip().upper().split()
        if not parts: return ""
        c = parts[0]
        
        if c in ["EXIT", "QUIT"]: 
            self.mgr.stop_event.set()
            return "EXIT"
        
        if c in ["WS", "WD", "H", "D", "P1", "P3", "P6", "P24", "T1", "T2", "T3", "T6", "T9", "T12", "T18", "T24"]:
            self.mode = c
            self.mode_expiry = time.time() + 30
            return f"Showing {c} for 30s"
             
        return "Unknown Cmd"

def main():
    mgr = StationManager()
    ui = MapUI(mgr)
    threading.Thread(target=mgr.background_crawler, daemon=True).start()
    ui.draw()
    
    import termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    new_settings = termios.tcgetattr(fd)
    new_settings[3] = new_settings[3] & ~termios.ICANON & ~termios.ECHO
    
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        while not mgr.stop_event.is_set():
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                char = sys.stdin.read(1)
                if char in ('\r', '\n'): 
                    cmd = ui.input_buffer
                    ui.input_buffer = ""
                    res = ui.handle_command(cmd)
                    if res == "EXIT": break
                    ui.draw(res)
                elif char in ('\x7f', '\x08'): 
                    ui.input_buffer = ui.input_buffer[:-1]
                    ui.draw()
                elif ord(char) == 3: 
                    break
                else:
                    ui.input_buffer += char
                    ui.draw()
            elif mgr.last_data_change > ui.last_draw_time or (ui.mode != "TEMP" and time.time() > ui.mode_expiry - 1):
                ui.draw()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__": main()
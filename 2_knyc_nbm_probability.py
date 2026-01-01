#!/usr/bin/env python3
import sys
import os
import time
import datetime
import re
import subprocess
import shutil
import traceback

if sys.version_info < (3, 6):
    print("ERROR: Python 3.6+ required.")
    sys.exit(1)

STATION_ID = "KNYC"
BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/blend/v4.3"
POLL_INTERVAL = 120

class Color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'
    GREY = '\033[90m'
    WHITE = '\033[97m'

def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

def to_eastern(utc_dt):
    """Converts UTC to Eastern Time (Approximation)."""
    is_dst = time.localtime().tm_isdst > 0
    offset = -4 if is_dst else -5
    return utc_dt + datetime.timedelta(hours=offset)

def get_target_cycle():
    now = get_utc_now()
    h = now.hour
    target_h = 19
    offset_days = -1
    
    if h >= 1:
        offset_days = 0
        target_h = 1
        if h >= 7: target_h = 7
        if h >= 13: target_h = 13
        if h >= 19: target_h = 19
        
    target_date = now + datetime.timedelta(days=offset_days)
    return target_date.strftime("%Y%m%d"), f"{target_h:02d}"

def get_previous_cycle(date_str, cycle_str):
    dt = datetime.datetime.strptime(f"{date_str} {cycle_str}", "%Y%m%d %H")
    prev_dt = dt - datetime.timedelta(hours=6)
    return prev_dt.strftime("%Y%m%d"), f"{prev_dt.hour:02d}"

def fetch_with_curl(date_str, cycle_str):
    filename = f"blend_nbptx.t{cycle_str}z"
    url = f"{BASE_URL}/blend.{date_str}/{cycle_str}/text/{filename}"
    
    cmd = [
        "curl", "-s", "-L", 
        "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--max-time", "15",
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if "<!DOCTYPE html>" in result.stdout or "404 Not Found" in result.stdout:
            return "NOT_FOUND", None
        if result.returncode != 0:
            return f"CURL_ERR_{result.returncode}", None
        if len(result.stdout) < 1000:
            return "NOT_FOUND", None
        return "SUCCESS", result.stdout
    except FileNotFoundError:
        return "CURL_MISSING", None
    except Exception as e:
        return f"SYS_ERROR: {e}", None

def extract_matrix(text):
    lines = text.splitlines()
    buffer = []
    capturing = False
    
    start_pattern = re.compile(rf"^\s*{STATION_ID}\s+NBM")
    stop_pattern = re.compile(r"^\s*[A-Z0-9]{3,6}\s+NBM")
    
    for line in lines:
        if not capturing:
            if start_pattern.match(line):
                capturing = True
                buffer.append(line)
        else:
            if stop_pattern.match(line) and not start_pattern.match(line):
                break
            buffer.append(line)
            
    return "\n".join(buffer) if buffer else None

def parse_tx_probability(matrix_text, cycle_date_str, cycle_hour_str):
    """
    Parses TXNP using FHR (Forecast Hour) row for exact dating.
    """
    if not matrix_text: return []
    
    lines = matrix_text.splitlines()
    fhr_line = None
    
    for line in lines:
        if line.strip().startswith("FHR"):
            fhr_line = line
            break
            
    if not fhr_line: return []

    cycle_dt = datetime.datetime.strptime(f"{cycle_date_str} {cycle_hour_str}", "%Y%m%d %H").replace(tzinfo=datetime.timezone.utc)
    col_map = [] 
    
    matches = list(re.finditer(r"\d{2,3}", fhr_line))
    
    for m in matches:
        fhr = int(m.group())
        valid_dt = cycle_dt + datetime.timedelta(hours=fhr)
        
        if valid_dt.hour == 0:
            col_map.append({
                'idx': m.start(), 
                'end_idx': m.end(), 
                'dt': valid_dt
            })

    data_by_time = {} 
    
    for line in lines:
        row_type = None
        if re.match(r"^\s*TXNP1", line): row_type = "p10"
        if re.match(r"^\s*TXNP2", line): row_type = "p20"
        if re.match(r"^\s*TXNP5", line): row_type = "p50"
        if re.match(r"^\s*TXNP7", line): row_type = "p70"
        if re.match(r"^\s*TXNP9", line): row_type = "p90"
        
        if row_type:
            val_matches = re.finditer(r"(-?\d{1,3})", line)
            for vm in val_matches:
                val = int(vm.group())
                center_idx = (vm.start() + vm.end()) / 2
                
                for col in col_map:
                    col_center = (col['idx'] + col['end_idx']) / 2
                    if abs(center_idx - col_center) < 4:
                        ts = col['dt']
                        if ts not in data_by_time:
                            data_by_time[ts] = {
                                'col_utc': ts, 
                                'p10': None, 'p20': None, 'p50': None, 'p70': None, 'p90': None
                            }
                        data_by_time[ts][row_type] = val
                        break
    
    result = []
    for ts in sorted(data_by_time.keys()):
        item = data_by_time[ts]
        if item['p50'] is not None:
            item['start_utc'] = item['col_utc'] - datetime.timedelta(hours=12)
            item['end_utc'] = item['col_utc'] + datetime.timedelta(hours=6)
            result.append(item)
            
    return result

def format_delta(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 0: return "PASSED"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def draw_dashboard(state):
    os.system('clear')
    
    now_utc = get_utc_now()
    now_et = to_eastern(now_utc)
    
    print(f"{Color.BLUE}{Color.BOLD}" + "="*80 + f"{Color.END}")
    print(f"{Color.BOLD} NOAA NBM TERMINAL {Color.END}{Color.GREY}// {STATION_ID} // TX PROBABILITY DISTRIBUTION{Color.END}".ljust(65) + f"{Color.CYAN}{now_et.strftime('%H:%M:%S ET')}{Color.END}")
    print(f"{Color.BLUE}" + "="*80 + f"{Color.END}")

    status_msg = state['status']
    status_color = Color.GREY
    
    if state['status'] == 'SCANNING': status_color = Color.YELLOW
    if state['status'] == 'SUCCESS': status_color = Color.GREEN
    if state['status'] == 'WAITING_NEW': 
        status_color = Color.PURPLE
        status_msg = "USING BACKUP"
    if 'ERR' in state['status']: status_color = Color.RED
    
    target_display = f"{state['target_date']} {state['target_cycle']}Z"
    cycle_display = "---"
    
    if state['using_backup']:
        cycle_display = f"{Color.YELLOW}BACKUP ({state['data_cycle']}Z){Color.END}"
    elif state['status'] == 'SUCCESS':
        cycle_display = f"{Color.GREEN}LIVE ({state['data_cycle']}Z){Color.END}"

    timer_display = f"{state['timer']}s" if state['timer'] > 0 else "NOW"
    
    print(f" {Color.GREY}TARGET CYCLE{Color.END}".ljust(25) + f" {Color.GREY}CURRENTLY SHOWING{Color.END}".ljust(25) + f" {Color.GREY}NEXT POLL{Color.END}")
    print(f" {Color.BOLD}{target_display}{Color.END}".ljust(33) + f" {Color.BOLD}{cycle_display}{Color.END}".ljust(43) + f" {Color.BOLD}{timer_display}{Color.END}")
    
    print(f"\n{Color.GREY}" + "-"*80 + f"{Color.END}")
    print(f"{Color.BOLD} RAW DATA STREAM{Color.END}")
    print(f"{Color.GREY}" + "-"*80 + f"{Color.END}")
    
    if state['matrix']:
        print(f"{Color.GREEN}{state['matrix']}{Color.END}")
    else:
        print(f"\n{Color.GREY}   [ No data available yet. Retrying... ]{Color.END}")

    if state['parsed_data']:
        print(f"\n{Color.GREY}" + "-"*80 + f"{Color.END}")
        title = "DAILY HIGH (TX) PROBABILITY SPREAD (18-HR WINDOW)"
        if state['using_backup']: title += " [BACKUP DATA]"
        
        print(f"{Color.BOLD} {title}{Color.END}")
        print(f"{Color.GREY}" + "-"*80 + f"{Color.END}")
        
        print(f"{Color.GREY} {'VALID PERIOD (ET)':<40} {'10%':<5} {'20%':<5} {'50%':<5} {'70%':<5} {'90%':<5} {'STATUS'}{Color.END}")
        
        next_event_start = None
        next_event_end = None
        active_found = False
        
        for item in state['parsed_data']:
            start_et = to_eastern(item['start_utc'])
            end_et = to_eastern(item['end_utc'])
            
            period_str = f"{start_et.strftime('%a %m/%d %I%p')} - {end_et.strftime('%a %m/%d %I%p')}"
            
            is_active = item['start_utc'] <= now_utc <= item['end_utc']
            is_future = now_utc < item['start_utc']
            
            row_color = Color.WHITE
            status_text = "PASSED"
            
            if is_active:
                row_color = Color.CYAN + Color.BOLD
                status_text = "ACTIVE"
                if not active_found:
                    next_event_end = ("End of Current Window", item['end_utc'] - now_utc)
                    active_found = True
            elif is_future:
                row_color = Color.WHITE
                status_text = "UPCOMING"
                if next_event_start is None:
                    next_event_start = (f"Start of {start_et.strftime('%a')} Window", item['start_utc'] - now_utc)
                if next_event_end is None and not active_found:
                    next_event_end = (f"End of {start_et.strftime('%a')} Window", item['end_utc'] - now_utc)

            p10 = item['p10'] if item['p10'] is not None else "--"
            p20 = item['p20'] if item['p20'] is not None else "--"
            p50 = item['p50'] if item['p50'] is not None else "--"
            p70 = item['p70'] if item['p70'] is not None else "--"
            p90 = item['p90'] if item['p90'] is not None else "--"
            
            print(f"{row_color} {period_str:<40} {p10:<5} {p20:<5} {p50:<5} {p70:<5} {p90:<5} {status_text}{Color.END}")

        print(f"\n{Color.GREY}" + "."*80 + f"{Color.END}")
        
        c1_str = "--:--:--"
        c1_lbl = "WAITING FOR NEXT WINDOW"
        if next_event_start:
            c1_lbl = next_event_start[0]
            c1_str = format_delta(next_event_start[1])
            
        c2_str = "--:--:--"
        c2_lbl = "WINDOW CLOSING TIME"
        if next_event_end:
            c2_lbl = next_event_end[0]
            c2_str = format_delta(next_event_end[1])
            
        print(f" {Color.YELLOW}{c1_lbl:<30}{Color.END}  |  {Color.PURPLE}{c2_lbl:<30}{Color.END}")
        print(f" {Color.BOLD}{c1_str:<30}{Color.END}  |  {Color.BOLD}{c2_str:<30}{Color.END}")

    if state['last_msg']:
        msg_color = Color.RED if "Error" in state['last_msg'] or "CURL" in state['last_msg'] else Color.CYAN
        if state['using_backup'] and "404" in state['last_msg']:
             msg_color = Color.YELLOW
        print(f"\n {msg_color}> {state['last_msg']}{Color.END}")

def run_loop():
    if not shutil.which("curl"):
        print(f"{Color.RED}CRITICAL: 'curl' command not found.{Color.END}")
        return

    state = {
        'target_date': '---', 'target_cycle': '--',
        'data_date': '---',   'data_cycle': '--',
        'status': 'INIT', 'timer': 0,
        'matrix': None, 'parsed_data': None,
        'last_msg': None, 'next_poll': 0,
        'using_backup': False
    }
    
    last_success_target = None
    
    while True:
        t_date, t_cycle = get_target_cycle()
        state['target_date'] = t_date
        state['target_cycle'] = t_cycle
        
        target_id = f"{t_date}_{t_cycle}"
        
        if last_success_target == target_id:
            state['status'] = 'SUCCESS'
            state['timer'] = 0
            state['using_backup'] = False
            state['last_msg'] = "Latest cycle captured. Waiting for next run."
            draw_dashboard(state)
            time.sleep(1)
            continue

        now_ts = time.time()
        
        if now_ts >= state['next_poll']:
            state['status'] = 'SCANNING'
            draw_dashboard(state) 
            
            result, text = fetch_with_curl(t_date, t_cycle)
            
            if result == 'SUCCESS':
                matrix = extract_matrix(text)
                if matrix:
                    state['matrix'] = matrix
                    state['parsed_data'] = parse_tx_probability(matrix, t_date, t_cycle)
                    state['status'] = 'SUCCESS'
                    state['data_date'] = t_date
                    state['data_cycle'] = t_cycle
                    state['using_backup'] = False
                    last_success_target = target_id
                    state['last_msg'] = f"New data received ({t_cycle}Z)."
                else:
                    state['status'] = 'PARSE_ERR'
                    state['last_msg'] = "File found, but KNYC missing."
                    state['next_poll'] = now_ts + 30
                    state['timer'] = 30
            elif result == 'NOT_FOUND':
                b_date, b_cycle = get_previous_cycle(t_date, t_cycle)
                res_backup, txt_backup = fetch_with_curl(b_date, b_cycle)
                if res_backup == 'SUCCESS':
                    matrix = extract_matrix(txt_backup)
                    if matrix:
                        state['matrix'] = matrix
                        state['parsed_data'] = parse_tx_probability(matrix, b_date, b_cycle)
                        state['status'] = 'WAITING_NEW'
                        state['data_date'] = b_date
                        state['data_cycle'] = b_cycle
                        state['using_backup'] = True
                        state['last_msg'] = f"Target {t_cycle}Z not released. Showing {b_cycle}Z."
                state['next_poll'] = now_ts + POLL_INTERVAL
                state['timer'] = POLL_INTERVAL
            else: 
                state['status'] = result
                state['next_poll'] = now_ts + 60
                state['timer'] = 60
                state['last_msg'] = f"Curl Error: {result}"
        else:
            state['timer'] = int(state['next_poll'] - now_ts)
        
        draw_dashboard(state)
        time.sleep(1)

if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit()
    except Exception as e:
        print(f"\n{Color.RED}FATAL CRASH: {e}{Color.END}")
        traceback.print_exc()
        print("\nPress Enter to exit...")
        input()
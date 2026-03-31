# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/monitor/data_storage.py
import json
from datetime import datetime, timedelta
import os

# ---------------------------------------------------------------------------
# Period definitions — maps period key to window duration in minutes
# ---------------------------------------------------------------------------
PERIODS = {
    "15m":  15,
    "30m":  30,
    "1h":   60,
    "12h":  720,
    "1d":   1440,
    "7d":   10080,
    "30d":  43200,
}
# Maximum storage window is 30 days; we keep minute-resolution entries so
# fetching any sub-range is just a slice of the same list.
MAX_AGE_MINUTES = PERIODS["30d"]


class HistoricalDataStorage:
    def __init__(self, filename="/app/monitor/data/historical_data.json"):
        self.filename = filename
        self.max_age_days = 7
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        self.ensure_file_exists()

    def ensure_file_exists(self):
        """Initialize the JSON file with proper structure if it doesn't exist"""
        if not os.path.exists(self.filename):
            initial_data = {
                "daily_messages": [],
                "hourly": [],
                "daily": [],
                "bytes_ticks": [],    # NEW: fine-grained bytes ticks (3-min intervals)
                "msg_ticks": [],      # NEW: fine-grained message rate ticks (3-min intervals)
            }
            self.save_data(initial_data)

    def load_data(self):
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                for key in ('daily_messages', 'hourly', 'daily', 'bytes_ticks', 'msg_ticks'):
                    if key not in data:
                        data[key] = []
                return data
        except Exception as e:
            print(f"Error loading data: {e}")
            return {
                "daily_messages": [],
                "hourly": [],
                "daily": [],
                "bytes_ticks": [],
                "msg_ticks": [],
            }

    def save_data(self, data):
        try:
            with open(self.filename, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")

    # ------------------------------------------------------------------
    # NEW: fine-grained tick storage (every 3 minutes)
    # ------------------------------------------------------------------
    def add_tick(self, bytes_received: float, bytes_sent: float,
                 msg_received: int, msg_sent: int):
        """Record a 3-minute-resolution tick for bytes and message counts."""
        data = self.load_data()
        ts = datetime.now().isoformat(timespec='seconds') + 'Z'
        data['bytes_ticks'].append({
            'ts': ts,
            'rx': bytes_received,
            'tx': bytes_sent,
        })
        data['msg_ticks'].append({
            'ts': ts,
            'rx': msg_received,
            'tx': msg_sent,
        })
        # Prune to 30 days
        cutoff = (datetime.now() - timedelta(minutes=MAX_AGE_MINUTES)).isoformat(timespec='seconds') + 'Z'
        data['bytes_ticks'] = [e for e in data['bytes_ticks'] if e['ts'] >= cutoff]
        data['msg_ticks'] = [e for e in data['msg_ticks'] if e['ts'] >= cutoff]
        self.save_data(data)

    def get_bytes_for_period(self, period: str):
        """Return bytes_ticks filtered to the requested period."""
        minutes = PERIODS.get(period, 60)
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec='seconds') + 'Z'
        data = self.load_data()
        ticks = [e for e in data['bytes_ticks'] if e['ts'] >= cutoff]
        return {
            'timestamps': [e['ts'] for e in ticks],
            'bytes_received': [e['rx'] for e in ticks],
            'bytes_sent': [e['tx'] for e in ticks],
        }

    def get_messages_for_period(self, period: str):
        """Return msg_ticks filtered to the requested period."""
        minutes = PERIODS.get(period, 60)
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec='seconds') + 'Z'
        data = self.load_data()
        ticks = [e for e in data['msg_ticks'] if e['ts'] >= cutoff]
        return {
            'timestamps': [e['ts'] for e in ticks],
            'msg_received': [e['rx'] for e in ticks],
            'msg_sent': [e['tx'] for e in ticks],
        }

    # ------------------------------------------------------------------
    # Legacy methods kept for backwards compatibility
    # ------------------------------------------------------------------
    def update_daily_messages(self, message_count: int):
        """Update daily message count"""
        data = self.load_data()
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        found = False
        for entry in data['daily_messages']:
            if entry['date'] == current_date:
                entry['count'] += message_count
                found = True
                break
        if not found:
            data['daily_messages'].append({'date': current_date, 'count': message_count})

        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        data['daily_messages'] = [e for e in data['daily_messages'] if e['date'] >= cutoff_date]
        self.save_data(data)

    def add_hourly_data(self, bytes_received: float, bytes_sent: float):
        """Add hourly byte rate data (legacy — also records fine tick)"""
        data = self.load_data()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        data['hourly'].append({
            'timestamp': current_time,
            'bytes_received': bytes_received,
            'bytes_sent': bytes_sent
        })
        cutoff_time = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
        data['hourly'] = [e for e in data['hourly'] if e['timestamp'] >= cutoff_time]
        self.save_data(data)

    def get_hourly_data(self):
        """Get hourly byte rate data (legacy)"""
        data = self.load_data()
        hourly_data = data.get('hourly', [])
        return {
            'timestamps': [e['timestamp'] for e in hourly_data],
            'bytes_received': [e['bytes_received'] for e in hourly_data],
            'bytes_sent': [e['bytes_sent'] for e in hourly_data],
        }

    def get_daily_messages(self):
        """Get daily message counts for the last 7 days (legacy)"""
        try:
            data = self.load_data()
            if not data['daily_messages']:
                return {'dates': [], 'counts': []}
            daily_data = sorted(data['daily_messages'], key=lambda x: x['date'])[-7:]
            return {
                'dates': [e['date'] for e in daily_data],
                'counts': [e['count'] for e in daily_data],
            }
        except Exception as e:
            print(f"Error getting daily messages: {e}")
            return {'dates': [], 'counts': []}

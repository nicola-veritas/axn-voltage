#!/usr/bin/env python3
"""
Neuro Notes - BrainBit EEG Data Recorder
Main Flask application with WebSocket support for real-time data streaming
"""

import os
import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

from device_manager import BrainBitManager
from data_storage import DataStorage

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize components
device_manager = BrainBitManager()
data_storage = DataStorage()


# Global state
recording_session = None
is_recording = False


@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Get current device and recording status"""
    return jsonify({
        'device_connected': device_manager.is_connected(),
        'device_info': device_manager.get_device_info(),
        'is_recording': is_recording,
        'session_info': recording_session
    })


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status_update', {
        'device_connected': device_manager.is_connected(),
        'is_recording': is_recording
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


@socketio.on('scan_devices')
def handle_scan_devices():
    """Scan for available BrainBit devices"""
    try:
        devices = device_manager.scan_devices()
        emit('devices_found', {'devices': devices})
    except Exception as e:
        emit('error', {'message': f'Device scan failed: {str(e)}'})


@socketio.on('connect_device')
def handle_connect_device(data):
    """Connect to a specific BrainBit device"""
    try:
        device_id = data.get('device_id')
        
        # Set up live data callback for continuous monitoring
        device_manager._data_callback = handle_live_data_chunk
        
        success = device_manager.connect_device(device_id)
        
        if success:
            # Start monitoring device status
            start_device_monitoring()
            emit('device_connected', {'device_info': device_manager.get_device_info()})
        else:
            emit('error', {'message': 'Failed to connect to device'})
    except Exception as e:
        emit('error', {'message': f'Connection failed: {str(e)}'})


@socketio.on('disconnect_device')
def handle_disconnect_device():
    """Disconnect from current device"""
    try:
        device_manager.disconnect()
        emit('device_disconnected')
    except Exception as e:
        emit('error', {'message': f'Disconnection failed: {str(e)}'})


@socketio.on('start_recording')
def handle_start_recording():
    """Start recording EEG data"""
    global is_recording, recording_session
    
    try:
        if not device_manager.is_connected():
            emit('error', {'message': 'No device connected'})
            return
        
        # Initialize recording session
        recording_session = {
            'start_time': datetime.utcnow().isoformat(),
            'device_info': device_manager.get_device_info(),
            'session_id': f"session_{int(time.time())}"
        }
        
        # Start data storage
        data_storage.start_session(recording_session)
        
        # Start recording from device (this sets up storage callback)
        device_manager.start_recording(data_callback=handle_storage_data_chunk)
        
        is_recording = True
        emit('recording_started', {'session_info': recording_session})
        
    except Exception as e:
        emit('error', {'message': f'Failed to start recording: {str(e)}'})


@socketio.on('stop_recording')
def handle_stop_recording():
    """Stop recording EEG data"""
    global is_recording, recording_session
    
    try:
        if not is_recording:
            emit('error', {'message': 'Not currently recording'})
            return
        
        # Stop device recording
        device_manager.stop_recording()
        
        # Finalize data storage
        session_file = data_storage.stop_session()
        
        is_recording = False
        
        emit('recording_stopped', {
            'session_file': session_file,
            'session_info': recording_session
        })
        
        recording_session = None
        
    except Exception as e:
        emit('error', {'message': f'Failed to stop recording: {str(e)}'})


def handle_live_data_chunk(data_chunk):
    """Handle live data for visualization (always active when connected)"""
    # Send real-time data to web interface for live visualization
    simplified_data = {
        'timestamp': data_chunk.get('timestamp'),
        'eeg_data': data_chunk.get('eeg_data', {}),  # Now expects dict with O1,O2,T3,T4
        'signal_strength': data_chunk.get('signal_strength', 0),
        'battery_level': data_chunk.get('battery_level', 0),
        'signal_quality': data_chunk.get('signal_quality', 'unknown'),
        'packet_number': data_chunk.get('packet_number'),
        'marker': data_chunk.get('marker')
    }
    
    socketio.emit('live_data', simplified_data)

def handle_storage_data_chunk(data_chunk):
    """Handle data for storage (only when recording)"""
    if is_recording:
        # Store data locally
        data_storage.add_data_chunk(data_chunk)


def start_device_monitoring():
    """Start monitoring device status in background thread"""
    def monitor():
        while device_manager.is_connected():
            status = device_manager.get_device_status()
            socketio.emit('device_status', status)
            time.sleep(1)  # Update every second
    
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()


if __name__ == '__main__':
    print("Starting Neuro Notes application...")
    print("Open http://localhost:5000 in your browser")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

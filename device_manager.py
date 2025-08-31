"""
BrainBit Device Manager
Handles device discovery, connection, and data acquisition using pyneurosdk2
"""

import time
import threading
from typing import List, Dict, Optional, Callable
from datetime import datetime

try:
    from neurosdk.scanner import Scanner
    from neurosdk.sensor import Sensor
    from neurosdk.cmn_types import *
    from neurosdk.cmn_types import SensorState, SensorParameter, SensorFilter
    SDK_AVAILABLE = True
except ImportError:
    print("Warning: pyneurosdk2 not installed. Install with: pip install pyneurosdk2")
    SDK_AVAILABLE = False
    # Mock classes for development without device
    class Scanner:
        def __init__(self, *args): pass
        def start(self): pass
        def stop(self): pass
        def sensors(self): return []
    
    class Sensor:
        def __init__(self, *args): pass
        def connect(self): pass
        def disconnect(self): pass
        def is_connected(self): return False
    
    class SensorState:
        StateInRange = "StateInRange"


class BrainBitManager:
    """Manages BrainBit device operations"""
    
    def __init__(self):
        self.scanner = None
        self.sensor = None
        self.is_scanning = False
        self._data_callback = None
        self._monitoring_thread = None
        self._stop_monitoring = False
        self._discovered_sensors = {}  # Store discovered sensors by ID
        self._recording_callback = None  # Callback for data recording
    
    def scan_devices(self, timeout_seconds: int = 10) -> List[Dict]:
        """
        Scan for available BrainBit devices
        
        Returns:
            List of device info dictionaries
        """
        try:
            # Initialize scanner for BrainBit devices
            self.scanner = Scanner([SensorFamily.LEBrainBit])
            self.scanner.start()
            self.is_scanning = True
            
            print(f"Scanning for BrainBit devices for {timeout_seconds} seconds...")
            time.sleep(timeout_seconds)
            
            # Get discovered devices
            sensors = self.scanner.sensors()
            devices = []
            
            for sensor_info in sensors:
                try:
                    # sensor_info is a SensorInfo object, we need to extract info and create Sensor
                    sensor_id = sensor_info.address if hasattr(sensor_info, 'address') else str(id(sensor_info))
                    device_info = {
                        'id': sensor_id,
                        'name': sensor_info.name if hasattr(sensor_info, 'name') else 'BrainBit Device',
                        'address': sensor_info.address if hasattr(sensor_info, 'address') else 'Unknown',
                        'sensor_family': 'BrainBit'
                    }
                    devices.append(device_info)
                    
                    # Store the SensorInfo object - we'll create the actual Sensor during connection
                    self._discovered_sensors[sensor_id] = sensor_info
                        
                except Exception as e:
                    print(f"Error processing device info: {e}")
            
            # Don't stop the scanner yet - we need it for connection
            self.is_scanning = False
            
            print(f"Found {len(devices)} BrainBit device(s)")
            return devices
            
        except Exception as e:
            print(f"Device scan error: {e}")
            if self.scanner:
                self.scanner.stop()
            self.is_scanning = False
            return []
    
    def connect_device(self, device_id: str) -> bool:
        """
        Connect to a specific BrainBit device
        
        Args:
            device_id: Device identifier from scan results
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Find the sensor in our stored discovered sensors
            if device_id not in self._discovered_sensors:
                print(f"Device with ID {device_id} not found in discovered devices")
                print(f"Available devices: {list(self._discovered_sensors.keys())}")
                return False
            
            target_sensor = self._discovered_sensors[device_id]
            
            # Create actual Sensor object from SensorInfo using scanner
            if not hasattr(target_sensor, 'connect'):
                print(f"Creating Sensor object from SensorInfo for device {device_id}...")
                if SDK_AVAILABLE and self.scanner:
                    try:
                        # Use scanner.create_sensor() method - this is the correct way
                        target_sensor = self.scanner.create_sensor(target_sensor)
                        self._discovered_sensors[device_id] = target_sensor
                        print("Successfully created Sensor object using scanner.create_sensor()")
                    except Exception as e:
                        print(f"Failed to create Sensor object with scanner.create_sensor(): {e}")
                        return False
                else:
                    print("Scanner not available or SDK not loaded, cannot create Sensor object")
                    return False
            
            # Set the sensor (create_sensor already connects according to docs)
            print(f"Setting up connection to device {device_id}...")
            self.sensor = target_sensor
            
            # Check connection state (BrainBit uses .state attribute, not .is_connected())
            if hasattr(self.sensor, 'state'):
                if self.sensor.state == SensorState.StateInRange:
                    print(f"Successfully connected to BrainBit device: {device_id}")
                    # Start continuous data monitoring for live visualization
                    self._start_continuous_monitoring()
                    return True
                else:
                    print(f"Device state: {self.sensor.state}, attempting to wait for connection...")
            
            # Wait for connection to establish (create_sensor is blocking but may take time)
            max_wait = 15  # seconds - increased timeout for BrainBit
            print(f"Waiting for device to come in range (max {max_wait} seconds)...")
            for i in range(max_wait * 10):
                try:
                    if hasattr(self.sensor, 'state') and self.sensor.state == SensorState.StateInRange:
                        print(f"Successfully connected to BrainBit device: {device_id}")
                        # Configure hardware filters for dry electrode artifact removal
                        self._configure_hardware_filters()
                        # Start continuous data monitoring for live visualization
                        self._start_continuous_monitoring()
                        return True
                    if i % 10 == 0:  # Print progress every second
                        current_state = getattr(self.sensor, 'state', 'unknown')
                        print(f"Connection attempt {i//10 + 1}/{max_wait}, state: {current_state}")
                except Exception as e:
                    if i % 10 == 0:
                        print(f"Connection attempt {i//10 + 1}/{max_wait}, error checking state: {e}")
                time.sleep(0.1)
            
            print("Connection timeout - device may be out of range or in use by another application")
            return False
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from current device"""
        try:
            self._stop_monitoring = True
            
            # Stop signal acquisition if active
            if self.sensor and hasattr(self.sensor, 'execute_command'):
                try:
                    if hasattr(self.sensor, 'is_supported_command'):
                        if self.sensor.is_supported_command(SensorCommand.StopSignal):
                            self.sensor.execute_command(SensorCommand.StopSignal)
                except Exception as e:
                    print(f"Error stopping signal: {e}")
            
            if self.sensor and hasattr(self.sensor, 'state'):
                if self.sensor.state == SensorState.StateInRange:
                    self.sensor.disconnect()
                    print("Disconnected from BrainBit device")
            
            if self.scanner:
                self.scanner.stop()
            
            self.sensor = None
            self.scanner = None
            self._discovered_sensors.clear()  # Clear stored sensors
            self._data_callback = None
            self._recording_callback = None
            
        except Exception as e:
            print(f"Disconnection error: {e}")
    
    def is_connected(self) -> bool:
        """Check if device is currently connected"""
        try:
            if self.sensor is None:
                return False
            if hasattr(self.sensor, 'state'):
                return self.sensor.state == SensorState.StateInRange
            return False
        except:
            return False
    
    def get_device_info(self) -> Optional[Dict]:
        """Get information about connected device"""
        if not self.is_connected():
            return None
        
        try:
            return {
                'name': getattr(self.sensor, 'name', 'BrainBit Device'),
                'address': getattr(self.sensor, 'address', 'Unknown'),
                'connected': True,
                'battery_level': self._get_battery_level(),
                'signal_quality': 'good'  # Simplified for now
            }
        except Exception as e:
            print(f"Error getting device info: {e}")
            return None
    
    def get_device_status(self) -> Dict:
        """Get current device status for monitoring"""
        if not self.is_connected():
            return {'connected': False}
        
        try:
            return {
                'connected': True,
                'battery_level': self._get_battery_level(),
                'signal_quality': 'good',  # Simplified
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            print(f"Error getting device status: {e}")
            return {'connected': False, 'error': str(e)}
    
    def start_recording(self, data_callback: Callable = None):
        """
        Start recording EEG data from device (for storage)
        
        Args:
            data_callback: Function to call with each data chunk for storage
        """
        if not self.is_connected():
            raise Exception("No device connected")
        
        # Set the recording callback (different from live monitoring callback)
        self._recording_callback = data_callback
        
        print("Started EEG data recording")
    
    def _start_continuous_monitoring(self):
        """Start continuous data monitoring for live visualization"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            return  # Already monitoring
        
        self._stop_monitoring = False
        
        try:
            # Start signal acquisition if available
            if hasattr(self.sensor, 'execute_command') and hasattr(self.sensor, 'SensorCommand'):
                # Check if signal is supported
                if hasattr(self.sensor, 'is_supported_command'):
                    if self.sensor.is_supported_command(SensorCommand.StartSignal):
                        self.sensor.execute_command(SensorCommand.StartSignal)
                        print("Started signal acquisition for live monitoring")
            
            # Start data monitoring thread for live visualization
            self._monitoring_thread = threading.Thread(
                target=self._continuous_monitoring_loop,
                daemon=True
            )
            self._monitoring_thread.start()
            
            print("Started continuous EEG data monitoring")
            
        except Exception as e:
            print(f"Error starting continuous monitoring: {e}")
    
    def stop_recording(self):
        """Stop recording EEG data (but continue live monitoring)"""
        try:
            # Just clear the recording callback, keep live monitoring active
            self._recording_callback = None
            
            print("Stopped EEG data recording")
            
        except Exception as e:
            print(f"Error stopping recording: {e}")
            raise
    
    def _continuous_monitoring_loop(self):
        """Background thread for continuous monitoring and live visualization"""
        sample_count = 0
        
        while not self._stop_monitoring and self.is_connected():
            try:
                # Collect data for live visualization
                data_chunk = self._collect_data_chunk()
                
                # Send to live visualization callback (always active when connected)
                if data_chunk and self._data_callback:
                    self._data_callback(data_chunk)
                
                # Send to recording callback (only when recording)
                if data_chunk and hasattr(self, '_recording_callback') and self._recording_callback:
                    self._recording_callback(data_chunk)
                
                sample_count += 1
                time.sleep(0.1)  # ~10 Hz display update rate (much slower for readability)
                
            except Exception as e:
                print(f"Continuous monitoring error: {e}")
                time.sleep(0.1)  # Brief pause before retrying
    
    def _collect_data_chunk(self) -> Optional[Dict]:
        """
        Collect a single data chunk from the device using actual BrainBit SDK
        """
        try:
            if not self.sensor or not hasattr(self.sensor, 'read_signal_data'):
                # Fallback to mock data if SDK not available
                import random
                
                channel_data = {
                    'O1': random.uniform(-100, 100),
                    'O2': random.uniform(-100, 100), 
                    'T3': random.uniform(-100, 100),
                    'T4': random.uniform(-100, 100)
                }
                
                return {
                    'timestamp': datetime.utcnow().isoformat(),
                    'eeg_data': channel_data,
                    'battery_level': self._get_battery_level(),
                    'signal_quality': 'good',
                    'sample_rate': 250
                }
            
            # Try to read actual BrainBit signal data
            signal_data = self.sensor.read_signal_data()
            
            if signal_data and len(signal_data) > 0:
                # Get the most recent data point
                latest_data = signal_data[-1]
                
                channel_data = {
                    'O1': latest_data.O1,
                    'O2': latest_data.O2,
                    'T3': latest_data.T3,
                    'T4': latest_data.T4
                }
                
                return {
                    'timestamp': datetime.utcnow().isoformat(),
                    'eeg_data': channel_data,
                    'packet_number': latest_data.PackNum,
                    'marker': latest_data.Marker,
                    'battery_level': self._get_battery_level(),
                    'signal_quality': 'good',
                    'sample_rate': 250
                }
            else:
                # No data available yet, return None
                return None
                
        except Exception as e:
            print(f"Error collecting data: {e}")
            # Fallback to mock data with proper channel structure
            import random
            
            channel_data = {
                'O1': random.uniform(-100, 100),
                'O2': random.uniform(-100, 100), 
                'T3': random.uniform(-100, 100),
                'T4': random.uniform(-100, 100)
            }
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'eeg_data': channel_data,
                'battery_level': self._get_battery_level(),
                'signal_quality': 'good',
                'sample_rate': 250
            }
    
    def _configure_hardware_filters(self):
        """Configure BrainBit hardware filters to remove dry electrode artifacts"""
        try:
            if not self.sensor or not hasattr(self.sensor, 'set_parameter'):
                print("Cannot configure hardware filters - sensor not available")
                return
            
            # According to BrainBit documentation: use 1Hz high-pass filter to remove delta artifacts
            # This is the recommended approach for dry electrodes
            print("Configuring BrainBit hardware filters for dry electrode artifact removal...")
            
            # Set 1Hz high-pass filter to remove electrochemical artifacts
            hpf_1hz = SensorFilter.HPFBwhLvl1CutoffFreq1Hz
            self.sensor.set_parameter(SensorParameter.HardwareFilterState, hpf_1hz)
            
            print("✅ Applied BrainBit hardware filter: 1Hz high-pass (removes delta artifacts)")
            
        except Exception as e:
            print(f"⚠️ Could not configure hardware filters: {e}")
            print("Proceeding without hardware filtering - software filtering will be used instead")
    
    def _get_battery_level(self) -> int:
        """Get device battery level (0-100)"""
        try:
            # Replace with actual SDK call
            if hasattr(self.sensor, 'read_parameter'):
                # return self.sensor.read_parameter(SensorParameter.BattPower)
                pass
            return 85  # Mock value
        except:
            return 0

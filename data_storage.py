"""
Data Storage Manager
Handles local storage of EEG data with chunking and JSON format
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional


class DataStorage:
    """Manages local storage of EEG recording data"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.current_session = None
        self.current_chunk = None
        self.chunk_size_minutes = 5  # Create new chunk every 5 minutes
        self.chunk_start_time = None
        self.data_buffer = []
        
        # Create data directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)
    
    def start_session(self, session_info: Dict):
        """
        Start a new recording session
        
        Args:
            session_info: Dictionary with session metadata
        """
        self.current_session = session_info.copy()
        self.current_session['chunks'] = []
        self.chunk_start_time = datetime.utcnow()
        self.data_buffer = []
        
        print(f"Started new recording session: {session_info['session_id']}")
    
    def add_data_chunk(self, data_chunk: Dict):
        """
        Add a data chunk to the current recording
        
        Args:
            data_chunk: Dictionary with EEG data and metadata
        """
        if not self.current_session:
            print("No active session. Call start_session first.")
            return
        
        # Add timestamp if not present
        if 'timestamp' not in data_chunk:
            data_chunk['timestamp'] = datetime.utcnow().isoformat()
        
        # Add to buffer
        self.data_buffer.append(data_chunk)
        
        # Check if we need to create a new chunk file
        if self._should_create_new_chunk():
            self._save_current_chunk()
            self._start_new_chunk()
    
    def stop_session(self) -> Optional[str]:
        """
        Stop the current recording session and save final data
        
        Returns:
            Path to the final session file
        """
        if not self.current_session:
            print("No active session to stop")
            return None
        
        # Save any remaining data in buffer
        if self.data_buffer:
            self._save_current_chunk()
        
        # Create final session file
        session_file = self._save_session_file()
        
        print(f"Recording session stopped. Data saved to: {session_file}")
        
        # Reset state
        self.current_session = None
        self.current_chunk = None
        self.data_buffer = []
        
        return session_file
    
    def get_session_files(self) -> List[str]:
        """Get list of all saved session files"""
        session_files = []
        
        if os.path.exists(self.data_dir):
            for filename in os.listdir(self.data_dir):
                if filename.endswith('_session.json'):
                    session_files.append(os.path.join(self.data_dir, filename))
        
        return sorted(session_files)
    
    def load_session(self, session_file: str) -> Optional[Dict]:
        """
        Load a previously saved session
        
        Args:
            session_file: Path to session file
            
        Returns:
            Session data dictionary or None if error
        """
        try:
            with open(session_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading session file {session_file}: {e}")
            return None
    
    def _should_create_new_chunk(self) -> bool:
        """Check if we should create a new chunk file"""
        if not self.chunk_start_time:
            return False
        
        # Check time-based chunking
        time_diff = datetime.utcnow() - self.chunk_start_time
        time_threshold = time_diff.total_seconds() > (self.chunk_size_minutes * 60)
        
        # Check size-based chunking (optional)
        size_threshold = len(self.data_buffer) > 1000  # Adjust as needed
        
        return time_threshold or size_threshold
    
    def _start_new_chunk(self):
        """Start a new data chunk"""
        self.chunk_start_time = datetime.utcnow()
        self.data_buffer = []
    
    def _save_current_chunk(self):
        """Save current data buffer as a chunk file"""
        if not self.data_buffer:
            return
        
        chunk_id = len(self.current_session['chunks']) + 1
        chunk_filename = f"{self.current_session['session_id']}_chunk_{chunk_id:03d}.json"
        chunk_path = os.path.join(self.data_dir, chunk_filename)
        
        # Prepare chunk data
        chunk_data = {
            'chunk_info': {
                'chunk_id': chunk_id,
                'session_id': self.current_session['session_id'],
                'start_time': self.chunk_start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'sample_count': len(self.data_buffer)
            },
            'data': self.data_buffer.copy()
        }
        
        # Save chunk file
        try:
            with open(chunk_path, 'w') as f:
                json.dump(chunk_data, f, indent=2)
            
            # Add chunk info to session
            chunk_info = {
                'chunk_id': chunk_id,
                'filename': chunk_filename,
                'start_time': self.chunk_start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'sample_count': len(self.data_buffer),
                'file_size': os.path.getsize(chunk_path)
            }
            
            self.current_session['chunks'].append(chunk_info)
            
            print(f"Saved chunk {chunk_id} with {len(self.data_buffer)} samples to {chunk_filename}")
            
        except Exception as e:
            print(f"Error saving chunk file: {e}")
    
    def _save_session_file(self) -> str:
        """Save the complete session metadata file"""
        session_filename = f"{self.current_session['session_id']}_session.json"
        session_path = os.path.join(self.data_dir, session_filename)
        
        # Add session summary
        self.current_session['end_time'] = datetime.utcnow().isoformat()
        self.current_session['total_chunks'] = len(self.current_session['chunks'])
        self.current_session['total_samples'] = sum(
            chunk['sample_count'] for chunk in self.current_session['chunks']
        )
        
        # Calculate total recording duration
        if self.current_session['chunks']:
            start_time = datetime.fromisoformat(self.current_session['start_time'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(self.current_session['end_time'].replace('Z', '+00:00'))
            duration = (end_time - start_time).total_seconds()
            self.current_session['duration_seconds'] = duration
        
        try:
            with open(session_path, 'w') as f:
                json.dump(self.current_session, f, indent=2)
            
            return session_path
            
        except Exception as e:
            print(f"Error saving session file: {e}")
            return session_path  # Return path even if save failed
    
    def export_session_csv(self, session_file: str, output_file: str = None) -> Optional[str]:
        """
        Export session data to CSV format
        
        Args:
            session_file: Path to session JSON file
            output_file: Output CSV file path (optional)
            
        Returns:
            Path to exported CSV file or None if error
        """
        try:
            import csv
            
            session_data = self.load_session(session_file)
            if not session_data:
                return None
            
            if not output_file:
                base_name = os.path.splitext(session_file)[0]
                output_file = f"{base_name}.csv"
            
            # Load all chunk data
            all_data = []
            for chunk_info in session_data['chunks']:
                chunk_file = os.path.join(self.data_dir, chunk_info['filename'])
                with open(chunk_file, 'r') as f:
                    chunk_data = json.load(f)
                    all_data.extend(chunk_data['data'])
            
            # Write CSV
            with open(output_file, 'w', newline='') as csvfile:
                if not all_data:
                    return output_file
                
                # Get headers from first data point
                fieldnames = ['timestamp']
                if 'eeg_data' in all_data[0]:
                    fieldnames.extend([f'eeg_ch_{i}' for i in range(len(all_data[0]['eeg_data']))])
                fieldnames.extend(['battery_level', 'signal_quality'])
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for data_point in all_data:
                    row = {'timestamp': data_point['timestamp']}
                    
                    # Add EEG channels
                    if 'eeg_data' in data_point:
                        for i, value in enumerate(data_point['eeg_data']):
                            row[f'eeg_ch_{i}'] = value
                    
                    row['battery_level'] = data_point.get('battery_level', '')
                    row['signal_quality'] = data_point.get('signal_quality', '')
                    
                    writer.writerow(row)
            
            print(f"Exported session data to CSV: {output_file}")
            return output_file
            
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return None

#!/usr/bin/env python3
"""
Quick start script for Neuro Notes
Handles setup and launches the application
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.7 or higher"""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 or higher required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    directories = ['data', 'templates']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    print("✅ Directories created")

def setup_environment():
    """Set up environment variables if needed"""
    env_file = Path('.env')
    if not env_file.exists():
        print("💡 No .env file found. Create one from env_template.txt for GitHub integration")
    else:
        print("✅ Environment file found")

def main():
    """Main setup and run function"""
    print("🧠 Neuro Notes - BrainBit EEG Recorder")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return
    
    # Install dependencies
    if not install_dependencies():
        return
    
    # Create directories
    create_directories()
    
    # Setup environment
    setup_environment()
    
    print("\n🚀 Starting Neuro Notes...")
    print("📱 Open your browser to: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop the application")
    print("-" * 40)
    
    # Import and run the main app
    try:
        from app import app, socketio
        socketio.run(app, debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Neuro Notes stopped")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed correctly")
    except Exception as e:
        print(f"❌ Error starting application: {e}")

if __name__ == "__main__":
    main()

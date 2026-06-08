#!/usr/bin/env python3
import socket
import struct
import time
import datetime
import os
import sys
import logging
from threading import Lock

class NTPServer:
    def __init__(self, time_file='simulation_time.txt', host='0.0.0.0', port=123):
        self.time_file = time_file
        self.host = host
        self.port = port
        self.file_lock = Lock()
        
        # NTP constants
        self.NTP_DELTA = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
        self.STRATUM = 2  # Secondary server (1 = primary reference clock)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def read_time_from_file(self):
        """Read time from simulation_time.txt and convert to Unix timestamp"""
        try:
            with self.file_lock:
                if not os.path.exists(self.time_file):
                    self.logger.error(f"Time file {self.time_file} not found")
                    return None
                
                with open(self.time_file, 'r') as f:
                    content = f.read().strip()
                
                if not content:
                    self.logger.warning(f"Time file {self.time_file} is empty")
                    return None
                
                # Parse ISO 8601 format from simulation
                dt = datetime.datetime.fromisoformat(content.replace('Z', '+00:00'))
                return dt.timestamp()
                        
        except Exception as e:
            self.logger.error(f"Error reading time file: {e}")
            return None

    def create_ntp_packet(self, originate_timestamp):
        """Create NTP response packet (48 bytes)"""
        # Get time from simulation file
        custom_time = self.read_time_from_file()
        if custom_time is None:
            # Fallback to system time if file not available
            self.logger.warning("Using system time as fallback")
            custom_time = time.time()
        
        # Current time for receive and transmit timestamps
        receive_time = time.time()
        transmit_time = time.time()
        
        # Convert to NTP timestamps (seconds since 1900-01-01)
        reference_timestamp = int(custom_time) + self.NTP_DELTA
        originate_timestamp_ntp = originate_timestamp
        receive_timestamp_ntp = int(receive_time) + self.NTP_DELTA
        transmit_timestamp_ntp = int(transmit_time) + self.NTP_DELTA
        
        # Build NTP packet manually (48 bytes)
        packet = bytearray(48)
        
        # Byte 0: LI (2 bits) | VN (3 bits) | Mode (3 bits)
        packet[0] = (0 << 6) | (4 << 3) | 4  # LI=0 (no alarm), VN=4, Mode=4 (server)
        
        # Byte 1: Stratum
        packet[1] = self.STRATUM
        
        # Byte 2: Poll
        packet[2] = 4  # ~16 seconds
        
        # Byte 3: Precision (signed 8-bit, but we need unsigned)
        packet[3] = 250  # -6 as unsigned 8-bit (256-6 = 250)
        
        # Bytes 4-7: Root Delay (fixed point 16.16)
        struct.pack_into('!I', packet, 4, 0)
        
        # Bytes 8-11: Root Dispersion (fixed point 16.16)
        struct.pack_into('!I', packet, 8, 0)
        
        # Bytes 12-15: Reference Identifier
        struct.pack_into('!I', packet, 12, 0)
        
        # Bytes 16-23: Reference Timestamp
        struct.pack_into('!I', packet, 16, reference_timestamp)
        struct.pack_into('!I', packet, 20, 0)  # Fractional part
        
        # Bytes 24-31: Originate Timestamp (from client)
        struct.pack_into('!I', packet, 24, originate_timestamp_ntp)
        struct.pack_into('!I', packet, 28, 0)  # Fractional part
        
        # Bytes 32-39: Receive Timestamp
        struct.pack_into('!I', packet, 32, receive_timestamp_ntp)
        struct.pack_into('!I', packet, 36, 0)  # Fractional part
        
        # Bytes 40-47: Transmit Timestamp
        struct.pack_into('!I', packet, 40, transmit_timestamp_ntp)
        struct.pack_into('!I', packet, 44, 0)  # Fractional part
        
        return bytes(packet)

    def start_server(self):
        """Start the NTP server"""
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            
            self.logger.info(f"NTP Server started on {self.host}:{self.port}")
            self.logger.info(f"Reading simulation time from: {self.time_file}")
            self.logger.info("Waiting for NTP requests...")
            
            while True:
                try:
                    # Receive request
                    data, addr = sock.recvfrom(48)
                    self.logger.debug(f"Received NTP request from {addr}")
                    
                    # Extract originate timestamp from client request (bytes 40-43)
                    if len(data) >= 44:  # Minimum to get originate timestamp
                        try:
                            originate_timestamp = struct.unpack('!I', data[40:44])[0]
                        except Exception as e:
                            self.logger.error(f"Error extracting timestamp: {e}")
                            originate_timestamp = 0
                    else:
                        self.logger.warning(f"Short packet received: {len(data)} bytes")
                        originate_timestamp = 0
                    
                    # Create and send response
                    response = self.create_ntp_packet(originate_timestamp)
                    sock.sendto(response, addr)
                    
                except socket.error as e:
                    self.logger.error(f"Socket error: {e}")
                except Exception as e:
                    self.logger.error(f"Error handling NTP request: {e}")
                    
        except PermissionError:
            self.logger.error(f"Permission denied. Port {self.port} requires root privileges.")
            self.logger.info("Try running with sudo or use a port > 1024")
            self.logger.info("Example: sudo python3 ntpserver.py")
            self.logger.info("Or: python3 ntpserver.py --port 12345")
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
        finally:
            if 'sock' in locals():
                sock.close()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Satellite Emulator NTP Server')
    parser.add_argument('--file', default='simulation_time.txt', 
                       help='Time file path (default: simulation_time.txt)')
    parser.add_argument('--host', default='0.0.0.0', 
                       help='Host to bind (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=123, 
                       help='Port to bind (default: 123)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check if time file exists
    if not os.path.exists(args.file):
        print(f"Warning: Time file '{args.file}' not found.")
        print("The server will use system time until the file is created by the satellite emulator.")
        print("Make sure the satellite emulator is running and updating this file.")
    
    server = NTPServer(args.file, args.host, args.port)
    
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\nShutting down NTP server...")
        sys.exit(0)

if __name__ == '__main__':
    main()

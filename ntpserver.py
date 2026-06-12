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

    def _to_ntp_ts(self, unix_time):
        """Unix float time -> (seconds, fraction) NTP timestamp parts"""
        seconds = int(unix_time) + self.NTP_DELTA
        fraction = int((unix_time % 1) * 4294967296) & 0xFFFFFFFF
        return seconds, fraction

    def create_ntp_packet(self, originate_raw):
        """Create NTP response packet (48 bytes).

        originate_raw: the 8 raw bytes of the client's Transmit Timestamp,
        echoed verbatim as the Originate Timestamp — clients reject replies
        where this doesn't byte-match what they sent (including fraction).
        """
        # Get time from simulation file
        custom_time = self.read_time_from_file()
        if custom_time is None:
            # Fallback to system time if file not available
            self.logger.warning("Using system time as fallback")
            custom_time = time.time()

        # Receive/Transmit are what clients use to set their clock — they
        # must carry the SIMULATED time, otherwise nodes sync to host time.
        ref_s, ref_f = self._to_ntp_ts(custom_time)
        rx_s, rx_f = self._to_ntp_ts(custom_time)
        tx_s, tx_f = self._to_ntp_ts(custom_time)

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
        struct.pack_into('!II', packet, 16, ref_s, ref_f)

        # Bytes 24-31: Originate Timestamp — echo the client's Transmit
        # Timestamp bytes verbatim
        packet[24:32] = originate_raw

        # Bytes 32-39: Receive Timestamp (simulated time)
        struct.pack_into('!II', packet, 32, rx_s, rx_f)

        # Bytes 40-47: Transmit Timestamp (simulated time)
        struct.pack_into('!II', packet, 40, tx_s, tx_f)

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
                    
                    # The client's Transmit Timestamp (bytes 40-47) must be
                    # echoed verbatim as our Originate Timestamp
                    if len(data) >= 48:
                        originate_raw = data[40:48]
                    else:
                        self.logger.warning(f"Short packet received: {len(data)} bytes")
                        originate_raw = bytes(8)

                    # Create and send response
                    response = self.create_ntp_packet(originate_raw)
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

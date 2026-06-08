# Satellite Emulator NTP Time Server - Complete Usage Guide

## Overview

This solution provides an NTP time server that serves simulation time from the satellite emulator to Linux clients on the network. The system consists of:

1. **Modified Scenario.py**: Writes simulation time to `simulation_time.txt`
2. **Standalone NTP Server**: Reads the time file and serves it via NTP protocol
3. **Linux Client Configuration**: Configures clients to sync with the NTP server every 32 seconds

## System Architecture

```
Satellite Emulator → Class/Scenario.py → simulation_time.txt
                                                    ↓
                                              ntpserver.py
                                                    ↓
                                            NTP Protocol (Port 123)
                                                    ↓
                                            Linux Clients (32s sync)
```

## Step 1: Start the Satellite Emulator

1. **Start your satellite emulator normally**:
   ```bash
   python3 SatelliteEmulatorAPI.py
   ```

2. **Load configuration and start simulation**:
   - Upload your TOML configuration file
   - Initialize the scenario
   - Start the simulation

   The emulator will now write the current simulation time to `simulation_time.txt` in ISO 8601 format.

## Step 2: Start the NTP Server


```bash
sudo python3 ntpserver.py
```


### NTP Server Options

```bash
# Basic usage
python3 ntpserver.py

# Custom time file location
python3 ntpserver.py --file /path/to/simulation_time.txt

# Custom host and port
python3 ntpserver.py --host 192.168.1.100 --port 123

# Verbose logging
python3 ntpserver.py --verbose

# Help
python3 ntpserver.py --help
```

### NTP Server Output

```
2024-01-15 10:30:45,123 - INFO - NTP Server started on 0.0.0.0:123
2024-01-15 10:30:45,123 - INFO - Reading simulation time from: simulation_time.txt
2024-01-15 10:30:45,123 - INFO - Waiting for NTP requests...
2024-01-15 10:30:47,456 - DEBUG - Received NTP request from 192.168.1.50:123
2024-01-15 10:30:47,456 - DEBUG - Sent NTP response to 192.168.1.50:123
```

## Step 3: Configure Linux Clients

### Method 1: Traditional NTP Daemon (Recommended)

1. **Install NTP**:
   ```bash
   # Ubuntu/Debian
   sudo apt update && sudo apt install ntp
   
   # RHEL/CentOS
   sudo yum install ntp
   ```

2. **Configure NTP** (`/etc/ntp.conf`):
   ```bash
   # Disable default NTP servers
   # server 0.pool.ntp.org iburst
   # server 1.pool.ntp.org iburst
   # server 2.pool.ntp.org iburst
   # server 3.pool.ntp.org iburst
   10.4.39.86
   # Add your NTP server
   server your-ntp-server-ip iburst
   
   # Set polling interval to 32 seconds (2^5)
   minpoll 5
   maxpoll 5
   
   # Other settings
   driftfile /var/lib/ntp/ntp.drift
   logfile /var/log/ntp.log
   ```

3. **Restart NTP service**:
   ```bash
   sudo systemctl restart ntp
   sudo systemctl enable ntp
   ```

4. **Check sync status**:
   ```bash
   ntpq -p
   ```

### Method 2: Using Custom Port

If you used a custom port (e.g., 12345), modify `/etc/ntp.conf`:
```bash
server your-ntp-server-ip iburst port 12345
minpoll 5
maxpoll 5
```

### Method 3: chrony (Alternative)

1. **Install chrony**:
   ```bash
   sudo apt install chrony
   ```

2. **Configure** (`/etc/chrony.conf`):
   ```bash
   server your-ntp-server-ip iburst
   minpoll 5
   maxpoll 5
   ```

3. **Restart chrony**:
   ```bash
   sudo systemctl restart chronyd
   sudo systemctl enable chronyd
   ```

## Step 4: Verification

### Check NTP Server Status

```bash
# Check if NTP server is running
sudo netstat -ulnp | grep :123

# Test NTP server manually
ntpdate -q your-ntp-server-ip
```

### Check Client Synchronization

```bash
# Check NTP peers
ntpq -p

# Check system time sync
timedatectl status

# Force immediate sync
sudo ntpdate -u your-ntp-server-ip
```

## Troubleshooting

### Common Issues

1. **Permission Denied (Port 123)**:
   ```bash
   # Solution: Run with sudo
   sudo python3 ntpserver.py
   
   # Or use custom port
   python3 ntpserver.py --port 12345
   ```

2. **Time File Not Found**:
   ```bash
   # Make sure satellite emulator is running
   # Check if simulation_time.txt exists
   ls -la simulation_time.txt
   
   # Verify file content
   cat simulation_time.txt
   ```

3. **Clients Not Syncing**:
   ```bash
   # Check firewall
   sudo ufw status
   sudo ufw allow 123/udp
   
   # Check NTP service status
   sudo systemctl status ntp
   
   # Check NTP logs
   tail -f /var/log/ntp.log
   ```

4. **Time Drift Issues**:
   ```bash
   # Check NTP statistics
   ntpdc -c monlist
   
   # Reset NTP
   sudo systemctl stop ntp
   sudo ntpdate -u your-ntp-server-ip
   sudo systemctl start ntp
   ```

### Debug Mode

Enable verbose logging on NTP server:
```bash
python3 ntpserver.py --verbose
```

### Network Testing

Test NTP connectivity:
```bash
# Test UDP connectivity
nc -u your-ntp-server-ip 123

# Test NTP protocol
ntpdate -d your-ntp-server-ip
```

## File Locations

- **Simulation Time File**: `simulation_time.txt` (created by satellite emulator)
- **NTP Server**: `ntpserver.py`
- **NTP Config**: `/etc/ntp.conf` (Linux clients)
- **NTP Logs**: `/var/log/ntp.log` (Linux clients)

## Security Considerations

1. **Network Access**: Restrict NTP server to trusted networks
2. **Firewall**: Only allow NTP traffic from authorized clients
3. **File Permissions**: Ensure `simulation_time.txt` has appropriate permissions
4. **Root Access**: NTP server on port 123 requires root privileges


## Advanced Configuration


### Custom Time File Format

The NTP server expects ISO 8601 format:
```
2024-01-15T10:30:45.123Z
```

### Monitoring and Logging

Monitor NTP server activity:
```bash
# Enable verbose logging
python3 ntpserver.py --verbose

# Monitor log file
tail -f /var/log/ntp.log

# Monitor network traffic
sudo tcpdump -i any port 123
```

## Summary

This solution provides a complete NTP time synchronization system for the satellite network emulator:

1. **Satellite emulator** writes simulation time to file
2. **NTP server** reads file and serves time via standard NTP protocol
3. **Linux clients** sync with simulation time every 32 seconds

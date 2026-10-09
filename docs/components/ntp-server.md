---
title: NTP server
nav_order: 3
parent: Components
---

A custom UDP NTP server that synchronizes VM clocks to the emulator's simulated time. It reads the current simulation timestamp from `simulation_time.txt` (updated by the emulator during runtime) and serves it to NTP clients. Falls back to system time if the file is unavailable.

```bash
# Default (port 123, requires root)
sudo python3 ntpserver.py

# Custom port (no root required)
python3 ntpserver.py --port 12345
```

The API server starts the NTP server automatically on port `12345`.

See [NTP server usage guide]({{ site.baseurl }}/components/ntp-usage/) for client configuration and troubleshooting.

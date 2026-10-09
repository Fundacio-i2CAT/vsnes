---
title: Installation
nav_order: 2
---

Follow these steps to set up VSNES on your machine:

### 1. System Requirements
- Linux-based operating system (tested on Ubuntu).
- Python 3.10 or later.
- Virtualization support (QEMU/KVM).

---

### 2. Install Required Packages

```bash
sudo install.sh
```

### 3. Fix for czml Library
The czml library requires a small fix. Open the file:

`sudo nano /usr/local/lib/python3.10/dist-packages/czml/czml.py`

> **Note:** Find the exact path with `pip3 show czml`

Replace:
```python
from pygeoif.geometry import as_shape as asShape
```
With:
```python
from pygeoif.factories import shape as asShape
```

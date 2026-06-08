/**
 * Configuration Window JavaScript
 * Handles the interactive functionality of the floating configuration window
 */

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const configWindow = document.getElementById('configWindow');
    const closeConfigWindow = document.getElementById('closeConfigWindow');
    const cancelConfigBtn = document.getElementById('cancelConfigBtn');
    const generateConfigBtn = document.getElementById('generateConfigBtn');
    const addSatelliteBtn = document.getElementById('addSatelliteBtn');
    const addGroundStationBtn = document.getElementById('addGroundStationBtn');
    const addChannelBtn = document.getElementById('addChannelBtn');
    
    // Initially hide the config window
    configWindow.style.display = 'none';
    
    // Add event listener to the "Gen Configuration" button to show the config window
    document.getElementById('genConfigBtn').addEventListener('click', function() {
        configWindow.style.display = 'flex';
        updateSummary();
    });
    
    // Close the config window
    closeConfigWindow.addEventListener('click', function() {
        configWindow.style.display = 'none';
    });
    
    // Cancel button closes the config window
    cancelConfigBtn.addEventListener('click', function() {
        configWindow.style.display = 'none';
    });
    
    // Add event listeners to remove buttons
    document.querySelectorAll('.remove-system').forEach(button => {
        button.addEventListener('click', function() {
            const parentElement = this.closest('.satellite-system, .ground-station, .channel');
            if (parentElement) {
                // Don't remove if it's the last element of its type
                const container = parentElement.parentElement;
                if (container.children.length > 1) {
                    parentElement.remove();
                    updateSummary();
                } else {
                    showNotification('Cannot remove the last item', 'warning');
                }
            }
        });
    });
    
    // Add Satellite
    addSatelliteBtn.addEventListener('click', function() {
        const satelliteSystemsContainer = document.getElementById('satelliteSystemsContainer');
        const satelliteCount = satelliteSystemsContainer.children.length + 1;
        const newSatelliteId = `sat${satelliteCount}`;
        
        const newSatellite = document.createElement('div');
        newSatellite.className = 'satellite-system';
        newSatellite.innerHTML = `
            <div class="system-header">
                <h5 class="system-title">SATELLITE-${satelliteCount}</h5>
                <button class="btn-icon remove-system" aria-label="Remove satellite">
                    <img src="./assets/images/icons/delete.png" alt="Remove">
                </button>
            </div>
            
            <div class="form-group">
                <label for="${newSatelliteId}-name" class="form-label">Name</label>
                <input type="text" id="${newSatelliteId}-name" class="form-control" value="SATELLITE-${satelliteCount}">
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-propagator" class="form-label">Propagator</label>
                    <select id="${newSatelliteId}-propagator" class="form-control">
                        <option value="SGP4">SGP4</option>
                        <option value="TwoBody">TwoBody</option>
                    </select>
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-service" class="form-label">Service</label>
                    <select id="${newSatelliteId}-service" class="form-control">
                        <option value="Standard">Standard</option>
                        <option value="Relay">Relay</option>
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label for="${newSatelliteId}-group" class="form-label">Group</label>
                <input type="text" id="${newSatelliteId}-group" class="form-control" value="LEO">
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-os" class="form-label">OS</label>
                    <select id="${newSatelliteId}-os" class="form-control">
                        <option value="debian">Debian</option>
                        <option value="ubuntu">Ubuntu</option>
                        <option value="alpine">Alpine</option>
                    </select>
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-isvm" class="form-label">Is External VM</label>
                    <select id="${newSatelliteId}-isvm" class="form-control">
                        <option value="0">No (Internal)</option>
                        <option value="1">Yes (External)</option>
                    </select>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-username" class="form-label">Username</label>
                    <input type="text" id="${newSatelliteId}-username" class="form-control" value="debian">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-password" class="form-label">Password</label>
                    <input type="password" id="${newSatelliteId}-password" class="form-control" value="debian">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-ip" class="form-label">IP External</label>
                    <input type="text" id="${newSatelliteId}-ip" class="form-control" value="172.27.12.${100 + satelliteCount}">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newSatelliteId}-interface" class="form-label">Interface</label>
                    <input type="text" id="${newSatelliteId}-interface" class="form-control" value="eth0">
                </div>
            </div>
            
            <div class="form-group">
                <label for="${newSatelliteId}-vm-name" class="form-label">VM Name</label>
                <input type="text" id="${newSatelliteId}-vm-name" class="form-control" value="SATELLITE-${satelliteCount}">
            </div>
        `;
        
        satelliteSystemsContainer.appendChild(newSatellite);
        
        // Add event listener to the new remove button
        newSatellite.querySelector('.remove-system').addEventListener('click', function() {
            if (satelliteSystemsContainer.children.length > 1) {
                newSatellite.remove();
                updateSummary();
            } else {
                showNotification('Cannot remove the last satellite', 'warning');
            }
        });
        
        updateSummary();
    });
    
    // Add Ground Station
    addGroundStationBtn.addEventListener('click', function() {
        const groundStationsContainer = document.getElementById('groundStationsContainer');
        const stationCount = groundStationsContainer.children.length + 1;
        const newStationId = `gs${stationCount}`;
        
        const newGroundStation = document.createElement('div');
        newGroundStation.className = 'ground-station';
        newGroundStation.innerHTML = `
            <div class="system-header">
                <h5 class="system-title">GS-${stationCount}</h5>
                <button class="btn-icon remove-system" aria-label="Remove ground station">
                    <img src="./assets/images/icons/delete.png" alt="Remove">
                </button>
            </div>
            
            <div class="form-group">
                <label for="${newStationId}-name" class="form-label">Name</label>
                <input type="text" id="${newStationId}-name" class="form-control" value="GS-${stationCount}">
            </div>
            
            <div class="form-group">
                <label for="${newStationId}-group" class="form-label">Group</label>
                <input type="text" id="${newStationId}-group" class="form-control" value="GS">
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 32%;">
                    <label for="${newStationId}-latitude" class="form-label">Latitude</label>
                    <input type="number" id="${newStationId}-latitude" class="form-control" value="41.38732849041236" step="0.000001">
                </div>
                
                <div class="form-group" style="width: 32%;">
                    <label for="${newStationId}-longitude" class="form-label">Longitude</label>
                    <input type="number" id="${newStationId}-longitude" class="form-control" value="2.1118426322937003" step="0.000001">
                </div>
                
                <div class="form-group" style="width: 32%;">
                    <label for="${newStationId}-height" class="form-label">Height</label>
                    <input type="number" id="${newStationId}-height" class="form-control" value="15">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-os" class="form-label">OS</label>
                    <select id="${newStationId}-os" class="form-control">
                        <option value="debian">Debian</option>
                        <option value="ubuntu">Ubuntu</option>
                        <option value="alpine">Alpine</option>
                    </select>
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-isvm" class="form-label">Is External VM</label>
                    <select id="${newStationId}-isvm" class="form-control">
                        <option value="0">No (Internal)</option>
                        <option value="1">Yes (External)</option>
                    </select>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-interface" class="form-label">Interface</label>
                    <input type="text" id="${newStationId}-interface" class="form-control" value="eth0">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-ip" class="form-label">IP External</label>
                    <input type="text" id="${newStationId}-ip" class="form-control" value="172.27.12.${103 + stationCount}">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-username" class="form-label">Username</label>
                    <input type="text" id="${newStationId}-username" class="form-control" value="debian">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newStationId}-password" class="form-label">Password</label>
                    <input type="password" id="${newStationId}-password" class="form-control" value="debian">
                </div>
            </div>
            
            <div class="form-group">
                <label for="${newStationId}-vm-name" class="form-label">VM Name</label>
                <input type="text" id="${newStationId}-vm-name" class="form-control" value="GS-${stationCount}">
            </div>
        `;
        
        groundStationsContainer.appendChild(newGroundStation);
        
        // Add event listener to the new remove button
        newGroundStation.querySelector('.remove-system').addEventListener('click', function() {
            if (groundStationsContainer.children.length > 1) {
                newGroundStation.remove();
                updateSummary();
            } else {
                showNotification('Cannot remove the last ground station', 'warning');
            }
        });
        
        updateSummary();
    });
    
    // Add Channel
    addChannelBtn.addEventListener('click', function() {
        const channelsContainer = document.getElementById('channelsContainer');
        const channelCount = channelsContainer.children.length + 1;
        const newChannelId = `ch${channelCount}`;
        
        const newChannel = document.createElement('div');
        newChannel.className = 'channel';
        newChannel.innerHTML = `
            <div class="system-header">
                <h5 class="system-title">Channel ${channelCount}</h5>
                <button class="btn-icon remove-system" aria-label="Remove channel">
                    <img src="./assets/images/icons/delete.png" alt="Remove">
                </button>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-node1" class="form-label">Node 1</label>
                    <input type="text" id="${newChannelId}-node1" class="form-control" value="LEO">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-node2" class="form-label">Node 2</label>
                    <input type="text" id="${newChannelId}-node2" class="form-control" value="GS">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-elevation" class="form-label">Min Elevation Angle (deg)</label>
                    <input type="number" id="${newChannelId}-elevation" class="form-control" value="0">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-threshold" class="form-label">Threshold (m)</label>
                    <input type="number" id="${newChannelId}-threshold" class="form-control" value="2e12">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-datarate" class="form-label">Data Rate (Mbit)</label>
                    <input type="number" id="${newChannelId}-datarate" class="form-control" value="10000">
                </div>
                
                <div class="form-group" style="width: 48%;">
                    <label for="${newChannelId}-packetloss" class="form-label">Packet Loss (%)</label>
                    <input type="number" id="${newChannelId}-packetloss" class="form-control" value="0" min="0" max="100" step="0.1">
                </div>
            </div>
            
            <div class="form-group">
                <label for="${newChannelId}-correlatedlosses" class="form-label">Correlated Losses (%)</label>
                <input type="number" id="${newChannelId}-correlatedlosses" class="form-control" value="0" min="0" max="100" step="0.1">
            </div>
        `;
        
        channelsContainer.appendChild(newChannel);
        
        // Add event listener to the new remove button
        newChannel.querySelector('.remove-system').addEventListener('click', function() {
            if (channelsContainer.children.length > 1) {
                newChannel.remove();
                updateSummary();
            } else {
                showNotification('Cannot remove the last channel', 'warning');
            }
        });
        
        updateSummary();
    });
    
    // Generate and download configuration
    generateConfigBtn.addEventListener('click', function() {
        const configToml = generateConfigToml();
        downloadTomlFile(configToml);
        showNotification('Configuration file generated and downloaded', 'normal');
    });
    
    // Generate and download docker-compose.yml
    const generateComposeBtn = document.getElementById('generateComposeBtn');
    generateComposeBtn.addEventListener('click', function() {
        const composeYml = generateDockerCompose();
        downloadFile(composeYml, 'docker-compose.yml');
        showNotification('docker-compose.yml generated and downloaded', 'normal');
    });
    
    // Update summary counts
    function updateSummary() {
        const satelliteCount = document.getElementById('satelliteSystemsContainer').children.length;
        const groundStationCount = document.getElementById('groundStationsContainer').children.length;
        const channelCount = document.getElementById('channelsContainer').children.length;
        
        document.getElementById('satelliteCount').textContent = satelliteCount;
        document.getElementById('groundStationCount').textContent = groundStationCount;
        document.getElementById('channelCount').textContent = channelCount;
        
        // Calculate simulation period
        const startDatetime = document.getElementById('startDatetimeInput').value;
        const endDatetime = document.getElementById('endDatetimeInput').value;
        
        if (startDatetime && endDatetime) {
            const start = new Date(startDatetime);
            const end = new Date(endDatetime);
            const diffMs = end - start;
            const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
            const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
            
            document.getElementById('simulationPeriod').textContent = `${diffHrs}h ${diffMins}m`;
        }
    }
    
    // Generate TOML configuration
    function generateConfigToml() {
        let toml = `network = '${document.getElementById('networkInput').value || '10.0.0.0/24'}'\n`;
        toml += `network_ext = '172.27.12.0/24'\n`;
        toml += `unicast_flooding = 0\n`;
        
        // Time section
        toml += '[Time]\n';
        toml += `\tTimeInterval = ${document.getElementById('timeIntervalInput').value || '1'} #[min]\n`;
        toml += `\tContact_speed = ${document.getElementById('contactSpeedInput').value || '20'}\n`;
        toml += `\tNon_contact_speed = ${document.getElementById('nonContactSpeedInput').value || '20'}\n`;
        
        // Format datetime values
        const startDatetime = document.getElementById('startDatetimeInput').value;
        const endDatetime = document.getElementById('endDatetimeInput').value;
        
        if (startDatetime) {
            const startDate = new Date(startDatetime);
            toml += `\tstart_datetime = '${startDate.toISOString().replace('T', ' ').substring(0, 19)}'\n`;
        } else {
            toml += `\tstart_datetime = '2024-08-18 18:10:00'\n`;
        }
        
        if (endDatetime) {
            const endDate = new Date(endDatetime);
            toml += `\tend_datetime = '${endDate.toISOString().replace('T', ' ').substring(0, 19)}'\n`;
        } else {
            toml += `\tend_datetime = '2024-08-18 20:15:00'\n`;
        }
        
        // Space Segment section
        toml += '[SpaceSegment]\n';
        toml += `\tTLE = '${document.getElementById('tlePathInput').value || 'test.tle'}'\n`;
        
        // Satellite Systems
        const satelliteSystems = document.getElementById('satelliteSystemsContainer').children;
        for (let i = 0; i < satelliteSystems.length; i++) {
            const sat = satelliteSystems[i];
            const satId = `sat${i+1}`;
            
            toml += `\t[[SpaceSegment.SatelliteSistem]]\n`;
            toml += `\t\tpropagator = '${getValueById(sat, `${satId}-propagator`) || 'SGP4'}' \t#TwoBody or SGP4\n`;
            toml += `\t\tService = '${getValueById(sat, `${satId}-service`) || 'Standard'}' \t#Standard or Relay\n`;
            toml += `\t\tname = '${getValueById(sat, `${satId}-name`) || `SATELLITE-${i+1}`}' \n`;
            toml += `\t\tgroup = '${getValueById(sat, `${satId}-group`) || 'LEO'}'\n`;
            toml += `\t\tOS = '${getValueById(sat, `${satId}-os`) || 'debian'}' \t#ubuntu o alpines\n`;
            toml += `\t\tusername = '${getValueById(sat, `${satId}-username`) || 'debian'}'\n`;
            toml += `\t\tpassword = '${getValueById(sat, `${satId}-password`) || 'debian'}'\n`;
            toml += `\t\tis_external_vm = ${getValueById(sat, `${satId}-isvm`) || '0'}\n`;
            toml += `\t\tip_ext = '${getValueById(sat, `${satId}-ip`) || `172.27.12.${101 + i}`}'\n`;
            toml += `\t\tinterface = '${getValueById(sat, `${satId}-interface`) || 'eth0'}'\n`;
            toml += `\t\t[SpaceSegment.SatelliteSistem.clone_VM]\n`;
            toml += `\t\t\tname_VM = '${getValueById(sat, `${satId}-vm-name`) || `SATELLITE-${i+1}`}' \n`;
        }
        
        // Ground Segment section
        toml += '[GroundSegment]\n';
        
        // Ground Stations
        const groundStations = document.getElementById('groundStationsContainer').children;
        for (let i = 0; i < groundStations.length; i++) {
            const gs = groundStations[i];
            const gsId = `gs${i+1}`;
            
            toml += `\t[[GroundSegment.GroundSistem]]\n`;
            toml += `\t\tname = '${getValueById(gs, `${gsId}-name`) || `GS-${i+1}`}'\n`;
            toml += `\t\tgroup = '${getValueById(gs, `${gsId}-group`) || 'GS'}'\n`;
            toml += `\t\tlatitude = ${getValueById(gs, `${gsId}-latitude`) || '41.38732849041236'}\n`;
            toml += `\t\tlongitude = ${getValueById(gs, `${gsId}-longitude`) || '2.1118426322937003'}\n`;
            toml += `\t\theight = ${getValueById(gs, `${gsId}-height`) || '15'}\n`;
            toml += `\t\tOS = '${getValueById(gs, `${gsId}-os`) || 'debian'}' #ubuntu o alpine\n`;
            toml += `\t\tusername = '${getValueById(gs, `${gsId}-username`) || 'debian'}'\n`;
            toml += `\t\tpassword = '${getValueById(gs, `${gsId}-password`) || 'debian'}'\n`;
            toml += `\t\tis_external_vm = ${getValueById(gs, `${gsId}-isvm`) || '0'}\n`;
            toml += `\t\tip_ext = '${getValueById(gs, `${gsId}-ip`) || `172.27.12.${103 + i}`}'\n`;
            toml += `\t\tinterface = '${getValueById(gs, `${gsId}-interface`) || 'eth0'}'\n`;
            toml += `\t\t[GroundSegment.GroundSistem.clone_VM]\n`;
            toml += `\t\t\tname_VM = '${getValueById(gs, `${gsId}-vm-name`) || `GS-${i+1}`}' #\n`;
        }
        
        // Channels section
        toml += '[Channels]\n';
        
        // Channel entries
        const channels = document.getElementById('channelsContainer').children;
        for (let i = 0; i < channels.length; i++) {
            const ch = channels[i];
            const chId = `ch${i+1}`;
            
            toml += `\t[[Channels.Channel]]\n`;
            toml += `\t\tNode1 = '${getValueById(ch, `${chId}-node1`) || 'LEO'}' #Group name\n`;
            toml += `\t\tNode2 = '${getValueById(ch, `${chId}-node2`) || 'GS'}'\n`;
            toml += `\t\tMin_elevation_angle = ${getValueById(ch, `${chId}-elevation`) || '0'} \t#[deg]\n`;
            toml += `\t\tThreshold = ${getValueById(ch, `${chId}-threshold`) || '2e12'}\t\t#[m]\n`;
            toml += `\t\tData_rate =  ${getValueById(ch, `${chId}-datarate`) || '10000'}\t\t#[Mbit]\n`;
            toml += `\t\tPacket_loss = ${getValueById(ch, `${chId}-packetloss`) || '0'}\t\t#[%]\n`;
            toml += `\t\tCorrelated_losses = ${getValueById(ch, `${chId}-correlatedlosses`) || '0'}\t\t#[%] Emulate packet burst losses\n`;
        }
        
        return toml;
    }
    
    // Helper function to get value by ID within a parent element
    function getValueById(parentElement, id) {
        const element = parentElement.querySelector(`#${id}`);
        return element ? element.value : null;
    }
    
    // Download TOML file
    function downloadTomlFile(content) {
        downloadFile(content, 'config.toml');
    }
    
    // Generic file download
    function downloadFile(content, filename) {
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    
    // Generate docker-compose.yml from form data
    function generateDockerCompose() {
        // Parse network_ext subnet from the TOML form or use default
        const networkExt = '172.27.12.0/24';
        const subnetBase = networkExt.split('.')[2]; // "12"
        const subnetPrefix = `172.${networkExt.split('.')[1]}.${subnetBase}`;
        
        let services = '';
        let usedIps = [];
        
        // Satellites
        const satelliteSystems = document.getElementById('satelliteSystemsContainer').children;
        for (let i = 0; i < satelliteSystems.length; i++) {
            const sat = satelliteSystems[i];
            const satId = `sat${i+1}`;
            const name = getValueById(sat, `${satId}-name`) || `SATELLITE-${i+1}`;
            const isExternal = getValueById(sat, `${satId}-isvm`) || '0';
            const ip = getValueById(sat, `${satId}-ip`) || `${subnetPrefix}.${101 + i}`;
            
            // Only include external VMs in docker-compose
            if (isExternal === '1') {
                const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
                services += `  ${safeName}:\n`;
                services += `    build: ./docker\n`;
                services += `    container_name: ${name}\n`;
                services += `    hostname: ${name}\n`;
                services += `    cap_add:\n`;
                services += `      - NET_ADMIN\n`;
                services += `      - SYS_ADMIN\n`;
                services += `      - NET_RAW\n`;
                services += `    sysctls:\n`;
                services += `      - net.ipv4.ip_forward=1\n`;
                services += `    networks:\n`;
                services += `      vsnes:\n`;
                services += `        ipv4_address: ${ip}\n`;
                services += `    restart: unless-stopped\n`;
                usedIps.push(ip);
            }
        }
        
        // Ground Stations
        const groundStations = document.getElementById('groundStationsContainer').children;
        for (let i = 0; i < groundStations.length; i++) {
            const gs = groundStations[i];
            const gsId = `gs${i+1}`;
            const name = getValueById(gs, `${gsId}-name`) || `GS-${i+1}`;
            const isExternal = getValueById(gs, `${gsId}-isvm`) || '0';
            const ip = getValueById(gs, `${gsId}-ip`) || `${subnetPrefix}.${103 + i}`;
            
            if (isExternal === '1') {
                const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
                services += `  ${safeName}:\n`;
                services += `    build: ./docker\n`;
                services += `    container_name: ${name}\n`;
                services += `    hostname: ${name}\n`;
                services += `    cap_add:\n`;
                services += `      - NET_ADMIN\n`;
                services += `      - SYS_ADMIN\n`;
                services += `      - NET_RAW\n`;
                services += `    sysctls:\n`;
                services += `      - net.ipv4.ip_forward=1\n`;
                services += `    networks:\n`;
                services += `      vsnes:\n`;
                services += `        ipv4_address: ${ip}\n`;
                services += `    restart: unless-stopped\n`;
                usedIps.push(ip);
            }
        }
        
        let yml = `services:\n`;
        yml += services;
        yml += `\n`;
        yml += `networks:\n`;
        yml += `  vsnes:\n`;
        yml += `    name: vsnes_net\n`;
        yml += `    driver: bridge\n`;
        yml += `    ipam:\n`;
        yml += `      config:\n`;
        yml += `        - subnet: ${networkExt}\n`;
        
        return yml;
    }
    
    // Show notification
    function showNotification(message, type = 'normal') {
        const notificationContainer = document.getElementById('notificationContainer');
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        notificationContainer.appendChild(notification);
        
        // Remove notification after 3 seconds
        setTimeout(() => {
            notification.classList.add('notification-hide');
            setTimeout(() => {
                notificationContainer.removeChild(notification);
            }, 300);
        }, 3000);
    }
    
    // Initialize date/time inputs with default values
    const now = new Date();
    const startDate = new Date(now);
    startDate.setHours(startDate.getHours() + 1);
    startDate.setMinutes(0);
    startDate.setSeconds(0);
    
    const endDate = new Date(startDate);
    endDate.setHours(endDate.getHours() + 2);
    
    document.getElementById('startDatetimeInput').value = startDate.toISOString().slice(0, 16);
    document.getElementById('endDatetimeInput').value = endDate.toISOString().slice(0, 16);
    document.getElementById('networkInput').value = '10.0.0.0/24';
    
    // Initialize the summary
    updateSummary();
});
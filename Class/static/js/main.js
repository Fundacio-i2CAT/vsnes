/* -------------------------------------------------------------
   GLOBALS
----------------------------------------------------------------*/
const API_BASE_URL = "http://localhost:5050";

let reloadInterval = null;
let statusUpdateInterval = null;
let simulationRunning = false;

// Cesium / satellite-tracking globals
let viewer;                 // set in initializeCesium()
let czml;                   // CZML datasource
let satObjects = [];      // { entity, rec } pairs
let satrecs = [];      // parsed TLE records


/* -------------------------------------------------------------
   DOM-READY INITIALISATION
----------------------------------------------------------------*/
document.addEventListener("DOMContentLoaded", async () => {
    initializeInterface();
    initializeCesium();
    setupEventListeners();
    updateSimulationControls();
    getScenarioDescription();

    // Check if a simulation is already running and restore state
    try {
        const status = await getStatus(true);
        lastKnownStatus = status.system_status;
        
        if (status.system_status === 'RUNNING_SIMULATION') {
            simulationRunning = true;
            updateSimulationControls();
            startTimeSync();
            if (viewer && viewer.clock) {
                viewer.clock.shouldAnimate = true;
            }
            updateStatusDisplay('Simulation is running (restored on reload)', 'normal');
        } else if (status.system_status === 'PREPARING_VMS') {
            updateStatusDisplay('VMs are being prepared...', 'normal');
        }
    } catch (e) {
        console.warn("Could not restore simulation state on load:", e);
    }

    // Start watching for external state changes (MCP/API starts/stops)
    startExternalWatcher();
});

/* -------------------------------------------------------------
   BASIC UI INITIALISATION
----------------------------------------------------------------*/
function initializeInterface() {
    // File-input labels
    document.querySelectorAll(".file-input").forEach(input => {
        const fileNameDisplay = input.nextElementSibling.nextElementSibling;
        input.addEventListener("change", () => {
            fileNameDisplay.textContent = input.files.length ? input.files[0].name
                : "No file selected";
        });
    });

    updateStatusDisplay("System ready. Waiting for commands.");
}

/* -------------------------------------------------------------
   CESIUM INITIALISATION
----------------------------------------------------------------*/
function initializeCesium() {
    Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiIxMjUxZDk4OS1lMzdiLTQ3OTAtYWQ3Ny03OTE0OTYzNjlmNTEiLCJpZCI6ODg3OTIsImlhdCI6MTY0OTQwNTI4Mn0.nvrvhF553Lce6ANNU9r5U9HTwXD10Vq4IOdf32kGiIc';


    viewer = new Cesium.Viewer("cesiumContainer", {
        terrainProvider: Cesium.createWorldTerrain(),
        shouldAnimate: false,
        baseLayerPicker: false,
        skyBox: false,
        skyAtmosphere: false,
        contextOptions: {
            webgl: {
                alpha: true
            }
        }
    });

    // Remove default imagery
    viewer.imageryLayers.removeAll();

    // Add CartoDB Positron (Light)
    viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',
        credit: 'Map tiles by CartoDB, under CC BY 3.0. Data by OpenStreetMap, under ODbL.'
    }));

    // Set background to dark blue
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0b051aff");
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0b051aff");

    viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(0, 0, 20_000_000)
    });

    czml = new Cesium.CzmlDataSource();
    czml.load("ScenarioCZML.czml")
        .then(ds => viewer.dataSources.add(ds))
        .catch(err => console.error("Error loading CZML:", err));
}

/* -------------------------------------------------------------
   EVENT LISTENERS
----------------------------------------------------------------*/
function setupEventListeners() {
    // Control-panel toggle
    document.getElementById("toggleControlPanel")
        .addEventListener("click", toggleControlPanel);
    document.getElementById("closeControlPanel")
        .addEventListener("click", toggleControlPanel);

    // Config / TLE upload & API actions
    document.getElementById("uploadConfigBtn").addEventListener("click", uploadConfig);
    document.getElementById("uploadTLEBtn").addEventListener("click", uploadTLE);
    document.getElementById("loadConfigBtn").addEventListener("click", loadConfig);
    document.getElementById("initScenarioBtn").addEventListener("click", initScenario);
    document.getElementById("stopAllVMsBtn").addEventListener("click", stopAllVMs);
    document.getElementById("startSimulationBtn").addEventListener("click", startSimulation);
    document.getElementById("stopSimulationBtn").addEventListener("click", stopSimulation);
    document.getElementById("getStatusBtn").addEventListener("click", () => getStatus(false));

    /* ----------  TLE FILE INPUT  ---------- */
    document.getElementById("tleFile").addEventListener("change", e => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = ev => {
            satrecs = parseTLE(ev.target.result);
            showStatus("TLE file loaded. Click ‘Load & View TLE’.");  // helper
        };
        reader.readAsText(file);
    });

    /* ----------  NEW “LOAD & VIEW TLE” BUTTON  ---------- */
    document.getElementById("loadAndViewTLEBtn").addEventListener("click", () => {
        if (satrecs.length === 0) {
            showStatus("Please load a TLE file first.");
            return;
        }
        // Remove existing satellites
        satObjects.forEach(o => viewer.entities.remove(o.entity));
        satObjects = [];

        // Add new satellites
        satrecs.forEach(obj => satObjects.push(createSatEntity(obj)));

        viewer.scene.globe.depthTestAgainstTerrain = true;   // prevents clipping
        viewer.clock.multiplier = 60;  // 60× real time
        viewer.clock.shouldAnimate = true;

    });

    /* ----------  MANUAL RELOAD CZML BUTTON  ---------- */
    document.getElementById("reloadCzmlBtn").addEventListener("click", () => {
        Reload();
        showNotification("CZML manually reloaded", "success");
    });

    /* ----------  ONE GLOBAL CLOCK HANDLER FOR ALL SATS  ---------- */
    viewer.clock.onTick.addEventListener(() => {
        const now = Cesium.JulianDate.toDate(viewer.clock.currentTime);
        const gmst = satellite.gstime(now);

        satObjects.forEach(o => {
            const propagated = satellite.propagate(
                o.rec,
                now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate(),
                now.getUTCHours(), now.getUTCMinutes(), now.getUTCSeconds()
            ).position;
            if (!propagated) return;

            const ecf = satellite.eciToEcf(propagated, gmst);
            const pos = Cesium.Cartesian3.fromElements(ecf.x * 1e3, ecf.y * 1e3, ecf.z * 1e3);

            // **append** the sample instead of overwriting
            const julNow = Cesium.JulianDate.clone(viewer.clock.currentTime);
            o.posHistory.addSample(julNow, pos);
        });
    });

}

/* -------------------------------------------------------------
   SATELLITE HELPERS
----------------------------------------------------------------*/
function parseTLE(text) {
    const out = [];
    const lines = text.trim().split(/\r?\n/).filter(Boolean);

    for (let i = 0; i < lines.length;) {
        let name = "";
        if (lines[i][0] !== "1" && lines[i][0] !== "2") name = lines[i++];
        const l1 = lines[i++] || "";
        const l2 = lines[i++] || "";
        if (l1.startsWith("1") && l2.startsWith("2"))
            out.push({ name, rec: satellite.twoline2satrec(l1, l2) });
    }

    return out;
}

function createSatEntity({ name, rec }) {
    // Time-tagged position history
    const posHistory = new Cesium.SampledPositionProperty();

    const entity = viewer.entities.add({
        name: name || "Satellite",
        position: posHistory,                  // use the sampled property
        point: { pixelSize: 8, color: Cesium.Color.YELLOW },
        path: {
            show: true,
            trailTime: 86400,    // 24 h backward track
            leadTime: 0,        // no future track
            width: 2,
            resolution: 60,       // 60 s between rendered points
            material: Cesium.Color.CYAN.withAlpha(0.6)
        }
    });


    return { entity, rec, posHistory };


}


/* -------------------------------------------------------------
   SMALL STATUS / NOTIFICATION UTILITIES
----------------------------------------------------------------*/
function showStatus(msg) { updateStatusDisplay(msg, "normal"); }

function updateStatusDisplay(message, type = "normal") {
    const status = document.getElementById("statusMessage");
    if (!status) return;

    status.textContent = message;
    status.className = "status-message";           // reset
    status.classList.add(`status-${type}`);          // add new style
}

function showNotification(message, type = "success") {
    let container = document.getElementById("notificationContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "notificationContainer";
        container.className = "notification-container";
        document.body.appendChild(container);
    }

    const note = document.createElement("div");
    note.className = `notification notification-${type}`;
    note.textContent = message;
    container.appendChild(note);

    setTimeout(() => {
        note.classList.add("notification-hide");
        setTimeout(() => note.remove(), 300);
    }, 3_000);
}

/* -------------------------------------------------------------
   CONTROL-PANEL TOGGLE
----------------------------------------------------------------*/
function toggleControlPanel() {
    const panel = document.getElementById("controlPanel");
    const button = document.getElementById("toggleControlPanel");
    panel.classList.toggle("hidden");
    button.style.display = panel.classList.contains("hidden") ? "flex" : "none";
}

/* -------------------------------------------------------------
   SERVER-SIDE API FUNCTIONS  (uploadConfig / uploadTLE / loadConfig /
                               runSimulation / stopSimulation / getStatus)
   -- Unchanged from your previous version except where noted
----------------------------------------------------------------*/

/* ----------  Upload config.toml  ---------- */
async function uploadConfig() {
    const fileInput = document.getElementById('configFile');
    const file = fileInput.files[0];

    if (!file) {
        showStatus('Please select a configuration file first', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        updateStatusDisplay('Uploading configuration file...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/upload-config`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to upload configuration file');
        }

        const result = await response.json();
        showStatus(`Configuration uploaded successfully: ${result.message}`, 'success');
        updateStatusDisplay('Configuration file uploaded and ready to load', 'normal');

    } catch (error) {
        console.error('Error uploading config:', error);
        showStatus(`Failed to upload configuration: ${error.message}`, 'error');
        updateStatusDisplay('Error uploading configuration file', 'error');
    }
}

/* ----------  Upload TLE file  ---------- */
async function uploadTLE() {
    const fileInput = document.getElementById('tleFile');
    const file = fileInput.files[0];

    if (!file) {
        showStatus('Please select a TLE file first', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        updateStatusDisplay('Uploading TLE file...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/upload-tle`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to upload TLE file');
        }

        const result = await response.json();
        showStatus(`TLE file uploaded successfully: ${result.message}`, 'success');
        updateStatusDisplay('TLE file uploaded and ready for use', 'normal');

    } catch (error) {
        console.error('Error uploading TLE:', error);
        showStatus(`Failed to upload TLE file: ${error.message}`, 'error');
        updateStatusDisplay('Error uploading TLE file', 'error');
    }
}

/* ----------  Load config  ---------- */
async function loadConfig() {
    try {
        updateStatusDisplay('Loading configuration...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/load-config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load configuration');
        }

        const result = await response.json();
        showStatus(`Configuration loaded: ${result.message}`, 'success');

        // Update status display with configuration summary
        const summary = result.config_summary;
        let statusText = `Configuration loaded successfully!\n`;
        statusText += `Network: ${summary.network}\n`;
        statusText += `Satellites: ${summary.satellites}\n`;
        statusText += `Ground Stations: ${summary.ground_stations}\n`;
        statusText += `Channels: ${summary.channels}`;

        updateStatusDisplay(statusText, 'normal');

    } catch (error) {
        console.error('Error loading config:', error);
        showStatus(`Failed to load configuration: ${error.message}`, 'error');
        updateStatusDisplay('Error loading configuration', 'error');
    }
}

/* ----------  Init scenario  ---------- */
async function initScenario() {
    try {
        updateStatusDisplay('Initializing scenario...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/init-scenario`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to initialize scenario');
        }

        const result = await response.json();
        showStatus(`Scenario initialized: ${result.message}`, 'success');

        // Update status display with scenario info
        const info = result.scenario_info;
        let statusText = `Scenario initialized successfully!\n`;
        statusText += `Number of nodes: ${info.number_of_nodes}\n`;
        statusText += `Description: ${info.description}`;

        updateStatusDisplay(statusText, 'normal');

        // Reload CZML after scenario initialization
        Reload();

    } catch (error) {
        console.error('Error initializing scenario:', error);
        showStatus(`Failed to initialize scenario: ${error.message}`, 'error');
        updateStatusDisplay('Error initializing scenario', 'error');
    }
}

/* ----------  Stop all VMs  ---------- */
async function stopAllVMs() {
    try {
        updateStatusDisplay('Stopping all VMs...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/stop-vms`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to stop all VMs');
        }

        const result = await response.json();
        showStatus(`All VMs stopped: ${result.message}`, 'success');
        updateStatusDisplay('All VMs have been stopped', 'normal');

    } catch (error) {
        console.error('Error stopping all VMs:', error);
        showStatus(`Failed to stop all VMs: ${error.message}`, 'error');
        updateStatusDisplay('Error stopping all VMs', 'error');
    }
}

async function startSimulation() {
    try {
        const runVms = document.getElementById('runVmsCheckbox').checked;
        const password = prompt("Provide sudo password to run runtime_bash.sh (leave blank if password-less sudo is configured):");

        updateStatusDisplay('Starting simulation...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/simulation/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                generate_czml: true,
                run_vms: runVms,
                password: password || null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to start simulation');
        }

        const result = await response.json();
        showStatus(`Simulation started: ${result.message}`, 'success');
        updateStatusDisplay('Simulation is now running', 'normal');

        simulationRunning = true;
        updateSimulationControls();
        startTimeSync();

        // Start Cesium clock animation
        if (viewer && viewer.clock) {
            viewer.clock.shouldAnimate = true;
        }

        // Reload CZML to show updated simulation data
        Reload();

    } catch (error) {
        console.error('Error starting simulation:', error);
        showStatus(`Failed to start simulation: ${error.message}`, 'error');
        updateStatusDisplay('Error starting simulation', 'error');
    }
}

async function stopSimulation() {
    try {
        const password = prompt("Provide sudo password to run shutdown_bash.sh (leave blank if password-less sudo is configured):");
        
        updateStatusDisplay('Stopping simulation...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/simulation/stop`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ password: password || null })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to stop simulation');
        }

        const result = await response.json();
        showStatus(`Simulation stopped: ${result.message}`, 'success');
        updateStatusDisplay('Simulation has been stopped', 'normal');

        simulationRunning = false;
        updateSimulationControls();
        stopTimeSync();

        // Stop Cesium clock animation
        if (viewer && viewer.clock) {
            viewer.clock.shouldAnimate = false;
        }

    } catch (error) {
        console.error('Error stopping simulation:', error);
        showStatus(`Failed to stop simulation: ${error.message}`, 'error');
        updateStatusDisplay('Error stopping simulation', 'error');
    }
}

/* ----------  Get status ---------- */
async function getStatus(silent = false) {
    try {
        if (!silent) {
            updateStatusDisplay('Getting system status...', 'normal');
        }

        const response = await fetch(`${API_BASE_URL}/api/status`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to get status');
        }

        const status = await response.json();

        // Create detailed status message
        let statusText = `Status: ${status.system_status || 'Unknown'}\n`;
        statusText += `Scenario Loaded: ${status.scenario_loaded ? 'Yes' : 'No'}\n`;
        statusText += `Configuration Loaded: ${status.config_loaded ? 'Yes' : 'No'}\n`;
        statusText += `CZML Generated: ${status.is_czml_generated ? 'Yes' : 'No'}\n`;
        statusText += `Cesium Running: ${status.cesium_running ? 'Yes' : 'No'}`;

        if (status.number_of_nodes !== undefined) {
            statusText += `\nNodes: ${status.number_of_nodes}`;
        }

        if (status.simulation_time) {
            statusText += `\nSim Time: ${status.simulation_time}`;
        }

        if (!silent) {
            updateStatusDisplay(statusText, 'normal');
        }

        // Update sim time display if element exists
        const simDisplay = document.getElementById('simulationTimeDisplay');
        if (simDisplay) {
            simDisplay.textContent = status.simulation_time
                ? `Sim Time: ${status.simulation_time}`
                : 'Sim Time: N/A';
        }

        return status;

    } catch (error) {
        console.error('Error getting status:', error);
        const errorMsg = `Failed to get status: ${error.message}`;
        if (!silent) {
            showStatus(errorMsg, 'error');
            updateStatusDisplay('Error retrieving system status', 'error');
        }
        throw error;
    }
}

/* ----------  CZML reload helper ---------- */
function Reload() {
    viewer.dataSources.remove(czml);
    czml = new Cesium.CzmlDataSource();
    czml.load("ScenarioCZML.czml")
        .then(ds => {
            czml = ds;
            viewer.dataSources.add(czml);
            // Sync clock from CZML document packet
            if (ds.clock) {
                viewer.clock.currentTime = Cesium.JulianDate.clone(ds.clock.currentTime);
                viewer.clock.multiplier = ds.clock.multiplier || 60;
            }
            // Only animate if simulation is actually running
            viewer.clock.shouldAnimate = simulationRunning;
        })
        .catch(err => console.error("Error reloading CZML:", err));
}

/* ----------  Get current scenario description ---------- */
async function getScenarioDescription() {
    try {
        updateStatusDisplay('Getting scenario description...', 'normal');

        const response = await fetch(`${API_BASE_URL}/api/scenario`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to get scenario description');
        }

        const result = await response.json();

        // Create formatted description message
        let descriptionText = 'Current Scenario:\n\n';
        descriptionText += `Number of nodes: ${result.number_of_nodes}\n\n`;
        descriptionText += `Description:\n${result.description}`;

        updateStatusDisplay(descriptionText, 'normal');
        showStatus('Scenario description retrieved successfully', 'success');

        return result;

    } catch (error) {
        console.error('Error getting scenario description:', error);
        showStatus(`Failed to get scenario description: ${error.message}`, 'error');
        updateStatusDisplay('Error retrieving scenario description', 'error');
    }
}

/* ----------  Simulation buttons state ---------- */
function updateSimulationControls() {
    const startBtn = document.getElementById('startSimulationBtn');
    const stopBtn = document.getElementById('stopSimulationBtn');
    const runVmsCheckbox = document.getElementById('runVmsCheckbox');

    if (simulationRunning) {
        startBtn.disabled = true;
        //stopBtn.disabled = false;
        runVmsCheckbox.disabled = true;
        startBtn.classList.add('disabled');
        //stopBtn.classList.remove('disabled');
    } else {
        startBtn.disabled = false;
        //stopBtn.disabled = true;
        runVmsCheckbox.disabled = false;
        startBtn.classList.remove('disabled');
        //stopBtn.classList.add('disabled');
    }
}

/* ----------  Time Sync polling logic ---------- */
function startTimeSync() {
    if (statusUpdateInterval) clearInterval(statusUpdateInterval);
    statusUpdateInterval = setInterval(async () => {
        try {
            const status = await getStatus(true); // silent
            if (status.system_status === 'RUNNING_SIMULATION' && status.simulation_time) {
                const simTime = Cesium.JulianDate.fromIso8601(status.simulation_time);

                // Override Cesium clock to mathematically match Python backend
                viewer.clock.currentTime = simTime;

                // Update UI text element
                const simDisplay = document.getElementById('simulationTimeDisplay');
                if (simDisplay) {
                    simDisplay.textContent = `Sim Time: ${status.simulation_time}`;
                }
            }
        } catch (e) {
            console.error("Time sync poll failed", e);
        }
    }, 1000);
}

function stopTimeSync() {
    if (statusUpdateInterval) clearInterval(statusUpdateInterval);
    statusUpdateInterval = null;
    const simDisplay = document.getElementById('simulationTimeDisplay');
    if (simDisplay) {
        simDisplay.textContent = `Sim Time: N/A`;
    }
}

/* ----------  External state watcher ---------- */
// Lightweight polling that detects simulation state changes triggered externally
// (e.g., via MCP tools, API calls, or another browser tab)
let externalWatcherInterval = null;
let lastKnownStatus = null;

function startExternalWatcher() {
    if (externalWatcherInterval) clearInterval(externalWatcherInterval);
    externalWatcherInterval = setInterval(async () => {
        try {
            const status = await getStatus(true);
            const currentStatus = status.system_status;

            // Detect transition: idle → running
            if (lastKnownStatus !== 'RUNNING_SIMULATION' && currentStatus === 'RUNNING_SIMULATION') {
                console.log('[Watcher] Simulation started externally — activating Cesium');
                simulationRunning = true;
                updateSimulationControls();

                // Reload CZML to pick up new scenario data
                Reload();

                // Start time sync
                startTimeSync();

                // Animate
                if (viewer && viewer.clock) {
                    viewer.clock.shouldAnimate = true;
                }

                updateStatusDisplay('Simulation started externally — Cesium activated', 'normal');
            }

            // Detect transition: running → stopped/idle
            if (lastKnownStatus === 'RUNNING_SIMULATION' && currentStatus !== 'RUNNING_SIMULATION') {
                console.log('[Watcher] Simulation stopped externally');
                simulationRunning = false;
                updateSimulationControls();
                stopTimeSync();

                if (viewer && viewer.clock) {
                    viewer.clock.shouldAnimate = false;
                }

                updateStatusDisplay('Simulation stopped externally', 'normal');
            }

            // Detect CZML regeneration while running (e.g., new scenario loaded)
            if (currentStatus === 'RUNNING_SIMULATION' && status.is_czml_generated && !simulationRunning) {
                simulationRunning = true;
                updateSimulationControls();
                Reload();
                startTimeSync();
                if (viewer && viewer.clock) {
                    viewer.clock.shouldAnimate = true;
                }
            }

            lastKnownStatus = currentStatus;
        } catch (e) {
            // Silent fail — don't spam console every 3s
        }
    }, 3000); // Check every 3 seconds
}

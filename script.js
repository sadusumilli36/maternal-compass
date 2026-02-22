// Georgia County Interactive Map & Maternal Care Explorer

const GEORGIA_FIPS = '13';
const GEOJSON_URL = 'https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json';

// Initialize Map with constraints
const georgiaBounds = L.latLngBounds(
    L.latLng(30.355, -85.605), // Southwest
    L.latLng(35.000, -80.751)  // Northeast
);

const map = L.map('map', {
    maxBounds: georgiaBounds,
    maxBoundsViscosity: 1.0,
    zoomSnap: 0.1,
    keyboard: false
});

// Fit the map to Georgia's bounds and set that as the minimum zoom limit
map.fitBounds(georgiaBounds);
map.setMinZoom(map.getZoom());

// Light Theme Tiles
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

// Custom Reset Control
const ResetControl = L.Control.extend({
    options: {
        position: 'topleft'
    },
    onAdd: function (map) {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-custom');
        container.style.backgroundColor = 'white';
        container.style.width = '34px';
        container.style.height = '34px';
        container.style.display = 'flex';
        container.style.justifyContent = 'center';
        container.style.alignItems = 'center';
        container.style.cursor = 'pointer';
        container.title = 'Center Map';

        container.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                <path d="M3 3v5h5"/>
            </svg>
        `;

        container.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();
            map.fitBounds(georgiaBounds);
        };

        return container;
    }
});

map.addControl(new ResetControl());

// Expansion Plan Initialization
let expansionMap;
let expansionData = {}; // Store data by county name
let expansionDataByNormalized = {}; // Store same data by normalized county name
let activeExpansionCounty = null;
let expansionGeoJsonLayer;
let expansionPinMarker = null;
let expansionPinPlacementEnabled = false;
let activeCountyRiskData = null;

// Home Page County Data
let homeCountyData = {};
let hospitalMetrics = {}; // Store metrics from Updated ob_hospitals_with_level.csv

// Risk calculation constants and functions
const RISK_THRESHOLDS = {
    LOW: 0.77,
    MODERATE: 1.25,
    HIGH: 2.86
};

function calculateRiskFactor(prenatalPct, birthsPct, obBeds) {
    const beds = Math.max(parseInt(obBeds) || 0, 1);
    return (parseFloat(prenatalPct) * parseFloat(birthsPct)) / beds;
}

function getRiskLevelFromFactor(riskFactor) {
    const value = parseFloat(riskFactor);
    if (value <= RISK_THRESHOLDS.LOW) return 'Low';
    if (value <= RISK_THRESHOLDS.MODERATE) return 'Moderate';
    if (value <= RISK_THRESHOLDS.HIGH) return 'High';
    return 'Very High';
}

function simulateBedsAndRisk(prenatalPct, birthsPct, currentObBeds, currentRiskFactor, bedsToAdd) {
    const simulatedBeds = Math.max(parseInt(currentObBeds) || 0, 1) + Math.max(parseInt(bedsToAdd) || 0, 0);
    const numerator = parseFloat(prenatalPct) * parseFloat(birthsPct);
    const simulatedRiskFactor = numerator / simulatedBeds;
    const simulatedLevel = getRiskLevelFromFactor(simulatedRiskFactor);
    return {
        simulatedBeds,
        simulatedRiskFactor: parseFloat(simulatedRiskFactor.toFixed(3)),
        simulatedLevel
    };
}

function initExpansionMap() {
    if (!expansionMap) {
        expansionMap = L.map('expansion-map', {
            maxBounds: georgiaBounds,
            maxBoundsViscosity: 1.0,
            zoomSnap: 0.1,
            keyboard: false
        });

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(expansionMap);

        expansionMap.addControl(new ResetControl());

        // Load data first, then render geojson if available
        loadExpansionData().then(() => {
            if (geojson) {
                renderExpansionCounties();
            }
        });

        expansionMap.on('click', (e) => {
            placeExpansionPin(e.latlng);
        });

        expansionMap.fitBounds(georgiaBounds);
        expansionMap.setMinZoom(expansionMap.getZoom());

        // Handle window resize for this specific map
        window.addEventListener('resize', () => {
            if (document.getElementById('add-tab').classList.contains('active')) {
                expansionMap.invalidateSize();
                expansionMap.fitBounds(georgiaBounds);
            }
        });

    } else {
        setTimeout(() => {
            expansionMap.invalidateSize();
        }, 100);
    }
}

async function loadExpansionData() {
    try {
        const [expansionResponse, increaseResponse, lowRiskResponse, countyDataResponse] = await Promise.all([
            fetch('county_expansion_data.csv'),
            fetch('county_increase_10yr.csv'),
            fetch('beds_needed_for_low_risk_by_county(in).csv'),
            fetch('county_data.csv')
        ]);

        const expansionText = await expansionResponse.text();
        const expansionLines = expansionText.split('\n');

        const increaseText = await increaseResponse.text();
        const increaseLines = increaseText.split('\n');

        const lowRiskText = await lowRiskResponse.text();
        const lowRiskLines = lowRiskText.split('\n');

        const countyDataText = await countyDataResponse.text();
        const countyDataLines = countyDataText.split('\n');

        expansionData = {};
        expansionDataByNormalized = {};

        for (let i = 1; i < expansionLines.length; i++) {
            const line = expansionLines[i].trim();
            if (!line) continue;

            // County,Beds Needed,Old Risk
            const parts = line.split(',');
            if (parts.length >= 3) {
                const county = parts[0].trim();
                expansionData[county] = {
                    bedsNeeded: parts[1].trim(),
                    oldRisk: parts[2].trim(),
                    bedsToAdd10Years: null
                };

                expansionDataByNormalized[normalizeCountyName(county)] = expansionData[county];
            }
        }

        for (let i = 1; i < increaseLines.length; i++) {
            const line = increaseLines[i].trim();
            if (!line) continue;

            // COUNTY,Increase per 10 years
            const parts = line.split(',');
            if (parts.length >= 2) {
                const county = parts[0].trim();
                const bedsToAdd10Years = parseTenYearIncrease(parts[1]);
                const normalizedCounty = normalizeCountyName(county);

                if (!expansionDataByNormalized[normalizedCounty]) {
                    expansionData[county] = {
                        bedsNeeded: 'Unknown',
                        oldRisk: 'Unknown',
                        bedsToAdd10Years
                    };
                    expansionDataByNormalized[normalizedCounty] = expansionData[county];
                } else {
                    expansionDataByNormalized[normalizedCounty].bedsToAdd10Years = bedsToAdd10Years;
                }
            }
        }

        for (let i = 1; i < lowRiskLines.length; i++) {
            const line = lowRiskLines[i].trim();
            if (!line) continue;

            // county,state,current_ob_beds,beds_required_for_low_risk,additional_beds_needed,already_low_risk
            const parts = line.split(',');
            if (parts.length >= 6) {
                const county = parts[0].trim();
                const additionalBedsNeeded = parts[4].trim();
                const alreadyLowRisk = parts[5].trim().toUpperCase() === 'TRUE';
                const normalizedCounty = normalizeCountyName(county);

                if (!expansionDataByNormalized[normalizedCounty]) {
                    expansionData[county] = {
                        bedsNeeded: additionalBedsNeeded,
                        oldRisk: 'Unknown',
                        bedsToAdd10Years: null,
                        alreadyLowRisk
                    };
                    expansionDataByNormalized[normalizedCounty] = expansionData[county];
                } else {
                    expansionDataByNormalized[normalizedCounty].bedsNeeded = additionalBedsNeeded;
                    expansionDataByNormalized[normalizedCounty].alreadyLowRisk = alreadyLowRisk;
                }
            }
        }

        for (let i = 1; i < countyDataLines.length; i++) {
            const line = countyDataLines[i].trim();
            if (!line) continue;

            // county,pct_late_no_prenatal_care,pct_births_in_state,state,ob_beds,level,avg_distance_miles,fips,risk_factor
            const parts = line.split(',');
            if (parts.length >= 6) {
                const county = parts[0].trim();
                const level = parts[5].trim();
                const normalizedCounty = normalizeCountyName(county);

                if (!expansionDataByNormalized[normalizedCounty]) {
                    expansionData[county] = {
                        bedsNeeded: 'Unknown',
                        oldRisk: level || 'Unknown',
                        bedsToAdd10Years: null
                    };
                    expansionDataByNormalized[normalizedCounty] = expansionData[county];
                } else {
                    expansionDataByNormalized[normalizedCounty].oldRisk = level || expansionDataByNormalized[normalizedCounty].oldRisk;
                }
            }
        }
    } catch (err) {
        console.error('Error loading expansion data:', err);
    }
}

function normalizeCountyName(countyName) {
    return (countyName || '').toLowerCase().replace(/[^a-z]/g, '');
}

function parseTenYearIncrease(value) {
    const trimmedValue = (value || '').trim();
    const parsedValue = Number.parseFloat(trimmedValue);
    return Number.isFinite(parsedValue) ? parsedValue : null;
}

function createBedPinIcon(beds) {
    const label = Number.isFinite(beds) && beds >= 0 ? String(Math.round(beds)) : '';
    const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="36" height="56" viewBox="0 0 36 56">
            <path d="M18 2 C9.163 2 2 9.163 2 18 C2 28.5 18 40 18 40 C18 40 34 28.5 34 18 C34 9.163 26.837 2 18 2 Z"
                fill="#0F9D9A" stroke="#333" stroke-width="2"/>
            <circle cx="18" cy="17" r="9" fill="#fff" stroke="#333" stroke-width="1.5"/>
            <text x="18" y="21" text-anchor="middle" font-size="10" font-weight="700" fill="#0F9D9A">${label}</text>
            <text x="18" y="52" text-anchor="middle" font-size="10" font-weight="700" fill="#333">${label}</text>
        </svg>`;

    return L.divIcon({
        html: svg,
        className: '',
        iconSize: [36, 56],
        iconAnchor: [18, 52],
        popupAnchor: [0, -52]
    });
}

function clearExpansionPin(disablePlacement = true) {
    if (expansionPinMarker && expansionMap) {
        expansionMap.removeLayer(expansionPinMarker);
    }
    expansionPinMarker = null;
    if (disablePlacement) {
        expansionPinPlacementEnabled = false;
    }
}

function placeExpansionPin(latlng) {
    if (!activeExpansionCounty || !expansionPinPlacementEnabled) return;

    const bedsInput = document.getElementById('new-beds');
    const beds = bedsInput ? Number.parseFloat(bedsInput.value) : null;
    if (!Number.isFinite(beds) || beds <= 0) return;

    if (expansionPinMarker) {
        expansionPinMarker.setLatLng(latlng);
        expansionPinMarker.setIcon(createBedPinIcon(beds));
    } else {
        expansionPinMarker = L.marker(latlng, {
            icon: createBedPinIcon(beds),
            draggable: true
        });
        expansionPinMarker.addTo(expansionMap);
        expansionPinMarker.on('dragend', (e) => {
            placeExpansionPin(e.target.getLatLng());
        });
    }

}

function wireBedsInput() {
    const bedsInput = document.getElementById('new-beds');
    if (!bedsInput) return;

    bedsInput.oninput = () => {
        const beds = Number.parseFloat(bedsInput.value);
        if (!Number.isFinite(beds) || beds <= 0) {
            clearExpansionPin(false);
            const updatedRiskSpan = document.getElementById('updated-risk-value');
            if (updatedRiskSpan) {
                updatedRiskSpan.textContent = '—';
                updatedRiskSpan.className = 'value';
                updatedRiskSpan.style.color = 'var(--text-muted)';
            }
            return;
        }

        // Calculate updated risk
        if (activeCountyRiskData) {
            const simulation = simulateBedsAndRisk(
                activeCountyRiskData.prenatalPct,
                activeCountyRiskData.birthsPct,
                activeCountyRiskData.currentObBeds,
                activeCountyRiskData.currentRiskFactor,
                beds
            );

            const updatedRiskSpan = document.getElementById('updated-risk-value');
            if (updatedRiskSpan) {
                updatedRiskSpan.textContent = simulation.simulatedLevel;
                const riskClassName = `risk-${simulation.simulatedLevel.replace(/\s+/g, '')}`;
                updatedRiskSpan.className = `value ${riskClassName}`;
                updatedRiskSpan.style.padding = '0.2rem 0.5rem';
                updatedRiskSpan.style.borderRadius = '4px';
                updatedRiskSpan.style.display = 'inline-block';
                updatedRiskSpan.style.color = '';
            }
        }

        if (expansionPinMarker) {
            expansionPinMarker.setIcon(createBedPinIcon(beds));
        }
    };
}

function wireAddCenterButton() {
    const addCenterButton = document.getElementById('add-center-btn');
    const bedsInput = document.getElementById('new-beds');
    if (!addCenterButton || !bedsInput) return;

    addCenterButton.onclick = () => {
        const beds = Number.parseFloat(bedsInput.value);
        if (!Number.isFinite(beds) || beds <= 0) {
            bedsInput.focus();
            return;
        }
        expansionPinPlacementEnabled = true;
    };
}

function renderExpansionCounties() {
    // Similar to home map, but specific to Expansion interactions
    expansionGeoJsonLayer = L.geoJson(geojson.toGeoJSON(), {
        style: style,
        onEachFeature: function (feature, layer) {
            // Hover Tooltip
            layer.bindTooltip(feature.properties.NAME, {
                className: 'county-tooltip',
                sticky: true,
                direction: 'top',
                offset: [0, -10]
            });

            // Click to populate sidebar
            layer.on({
                click: (e) => {
                    if (expansionPinPlacementEnabled && activeExpansionCounty === e.target) {
                        placeExpansionPin(e.latlng);
                        return;
                    }
                    selectExpansionCounty(e.target, feature.properties.NAME);
                    placeExpansionPin(e.latlng);
                }
            });
        }
    }).addTo(expansionMap);
}

function selectExpansionCounty(layer, countyName) {
    if (activeExpansionCounty) {
        // Reset old layer style
        expansionGeoJsonLayer.resetStyle(activeExpansionCounty);
    }

    if (activeExpansionCounty && activeExpansionCounty !== layer) {
        clearExpansionPin();
    }

    // Populate Sidebar
    const data = expansionData[countyName]
        || expansionDataByNormalized[normalizeCountyName(countyName)]
        || { bedsNeeded: 'Unknown', oldRisk: 'Unknown', bedsToAdd10Years: null };

    // Store risk data for dynamic calculation
    const homeData = homeCountyData[countyName] || {};
    activeCountyRiskData = {
        prenatalPct: parseFloat(homeData.noPrenatalCare) || 0,
        birthsPct: parseFloat(homeData.birthPct) || 0,
        currentObBeds: parseInt(homeData.obBeds) || 0,
        currentRiskFactor: parseFloat(homeData.riskFactor) || 0,
        oldRiskLevel: data.oldRisk
    };

    // Highlight new layer
    highlightFeature(layer, data.oldRisk);
    activeExpansionCounty = layer;

    // Zoom to county
    expansionMap.fitBounds(layer.getBounds(), {
        padding: [50, 50],
        maxZoom: 10,
        animate: true
    });

    const tenYearBedsMarkup = Number.isFinite(data.bedsToAdd10Years)
        ? (data.bedsToAdd10Years > 0
            ? `<div class="beds-needed">OB beds per 100 births (10-yr): ${data.bedsToAdd10Years.toFixed(2)}</div>`
            : `<div class="beds-needed">No additional Beds needed.</div>`)
        : '';

    const sidebarContent = document.getElementById('expansion-sidebar-content');
    sidebarContent.innerHTML = `
        <div class="expansion-card-header">
            <h2>${countyName} County</h2>
            <div class="beds-needed">Beds Needed: ${data.bedsNeeded}</div>
            ${tenYearBedsMarkup}
        </div>

        <div class="add-center-section">
            <h3>Add Center</h3>
            <div class="draggable-pin" title="Drag to map (Coming Soon)">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                </svg>
            </div>
            
            <div class="input-group">
                <label for="new-beds">Number of Beds:</label>
                <input type="number" id="new-beds" placeholder="Enter planned beds..." min="0">
            </div>
            <button type="button" id="add-center-btn" class="add-center-btn">Add Center</button>
        </div>

        <div class="risk-comparison">
            <div class="risk-box">
                <span class="label">Old Risk</span>
                <span class="value risk-${data.oldRisk}" style="padding: 0.2rem 0.5rem; border-radius: 4px; display: inline-block;">${data.oldRisk}</span>
            </div>
            <div class="risk-box">
                <span class="label">Updated Risk</span>
                <span id="updated-risk-value" class="value" style="color: var(--text-muted); font-weight: normal;">&mdash;</span>
            </div>
        </div>
    `;

    wireBedsInput();
    wireAddCenterButton();

    // Optionally handle input change to calculate updated risk here
}

let geojson;
let clickedLayer;
let hospitalMarkers = L.layerGroup().addTo(map);
let allHospitals = [];
let maternalHospitals = [];

// Style for counties
function style(feature) {
    return {
        fillColor: '#0F9D9A',
        weight: 1,
        opacity: 1,
        color: 'rgba(10, 122, 120, 0.4)',
        fillOpacity: 0.15
    };
}

// Function to highlight a feature
function highlightFeature(layer, riskLevel) {
    const riskColor = getRiskColor(riskLevel);
    const riskGradient = getRiskGradientFill(layer, riskLevel);
    layer.setStyle({
        weight: 2.5,
        color: riskColor,
        fillOpacity: 0.6,
        fillColor: riskGradient
    });
    layer.bringToFront();
}

function normalizeRiskLevel(level) {
    return (level || '').toLowerCase().replace(/\s+/g, '');
}

function getRiskColor(level) {
    const normalized = normalizeRiskLevel(level);
    if (normalized === 'low') return '#2ECC71';
    if (normalized === 'moderate' || normalized === 'medium') return '#F1C40F';
    if (normalized === 'high') return '#E67E22';
    if (normalized === 'veryhigh') return '#E74C3C';
    if (normalized === 'critical') return '#8E2B0E';
    return '#0F9D9A';
}

function getRiskGradientFill(layer, level) {
    const normalized = normalizeRiskLevel(level) || 'default';
    const svg = getOverlaySvg(layer);
    if (!svg) return getRiskColor(level);

    const gradientId = `risk-gradient-${normalized}`;
    let defs = svg.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        svg.insertBefore(defs, svg.firstChild);
    }

    if (!svg.querySelector(`#${gradientId}`)) {
        const baseColor = getRiskColor(level);
        // Less lightening for moderate to keep it more yellow
        const lightFactor = normalized === 'moderate' ? 0.15 : 0.45;
        const lightColor = toGradientLightCustom(baseColor, lightFactor);
        const gradient = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
        gradient.setAttribute('id', gradientId);
        gradient.setAttribute('x1', '0%');
        gradient.setAttribute('y1', '0%');
        gradient.setAttribute('x2', '100%');
        gradient.setAttribute('y2', '100%');

        const stopStart = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
        stopStart.setAttribute('offset', '0%');
        stopStart.setAttribute('stop-color', lightColor);
        stopStart.setAttribute('stop-opacity', '0.95');

        const stopEnd = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
        stopEnd.setAttribute('offset', '100%');
        stopEnd.setAttribute('stop-color', baseColor);
        stopEnd.setAttribute('stop-opacity', '0.95');

        gradient.appendChild(stopStart);
        gradient.appendChild(stopEnd);
        defs.appendChild(gradient);
    }

    return `url(#${gradientId})`;
}

function getOverlaySvg(layer) {
    if (!layer || !layer._map) return null;
    return layer._map.getPanes().overlayPane.querySelector('svg');
}

function toGradientLight(hexColor) {
    return toGradientLightCustom(hexColor, 0.45);
}

function toGradientLightCustom(hexColor, lightFactor) {
    const rgb = hexToRgb(hexColor);
    if (!rgb) return hexColor;
    const mix = (channel) => Math.min(255, Math.round(channel + (255 - channel) * lightFactor));
    return `rgb(${mix(rgb.r)}, ${mix(rgb.g)}, ${mix(rgb.b)})`;
}

function hexToRgb(hexColor) {
    const normalized = (hexColor || '').replace('#', '');
    if (normalized.length !== 6) return null;
    const r = Number.parseInt(normalized.slice(0, 2), 16);
    const g = Number.parseInt(normalized.slice(2, 4), 16);
    const b = Number.parseInt(normalized.slice(4, 6), 16);
    if ([r, g, b].some((value) => Number.isNaN(value))) return null;
    return { r, g, b };
}

// Click interaction
function onEachFeature(feature, layer) {
    layer.bindTooltip(feature.properties.NAME, {
        className: 'county-tooltip',
        sticky: true,
        direction: 'top',
        offset: [0, -10]
    });

    layer.on({
        click: (e) => selectCounty(e.target, feature.properties)
    });
}

function selectCounty(layer, props, skipZoom = false) {
    if (clickedLayer) {
        geojson.resetStyle(clickedLayer);
    }
    clickedLayer = layer;
    const countyName = props.NAME;
    const data = homeCountyData[countyName] || {};
    highlightFeature(clickedLayer, data.level);
    updateInfoPanel(props);

    if (!skipZoom) {
        map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 9 });
    }
}

function updateInfoPanel(props) {
    const panel = document.getElementById('info-content');
    const countyName = props.NAME;
    const data = homeCountyData[countyName] || {};

    const levelRaw = data.level || 'Unknown';
    const distRaw = data.avgDistance || 'N/A';
    const bedsRaw = data.obBeds || '0';
    const careRaw = data.noPrenatalCare || 'N/A';

    panel.innerHTML = `
        <div class="county-info">
            <h2 style="color: var(--accent); font-size: 2.2rem; margin-bottom: 0.25rem;">${countyName} County</h2>
            <p style="color: var(--text-muted); font-size: 1rem; margin-bottom: 2rem;">FIPS Code: ${props.STATE}${props.COUNTY}</p>
            
            <div class="info-grid" style="margin-bottom: 2rem;">
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600; font-size: 0.8rem; letter-spacing: 0.5px;">LEVEL OF RISK</span>
                    <span class="info-value" style="font-size: 1.1rem; color: var(--text);">${levelRaw}</span>
                </div>
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600; font-size: 0.8rem; letter-spacing: 0.5px;">AVG DISTANCE TO HOSPITAL</span>
                    <span class="info-value" style="font-size: 1.1rem; color: var(--text);">${distRaw !== 'N/A' ? distRaw + ' miles' : 'N/A'}</span>
                </div>
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600; font-size: 0.8rem; letter-spacing: 0.5px;">OBSTETRIC BEDS</span>
                    <span class="info-value" style="font-size: 1.1rem; color: var(--text);">${bedsRaw}</span>
                </div>
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600; font-size: 0.8rem; letter-spacing: 0.5px;">LATE/NO PRENATAL CARE</span>
                    <span class="info-value" style="font-size: 1.1rem; color: var(--text);">${careRaw !== 'N/A' ? careRaw + '%' : 'N/A'}</span>
                </div>
            </div>

            <div class="maternal-facilities-list">
                <h3 style="color: var(--primary); opacity: 0.8; margin-top: 2rem; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">MATERNAL CARE FACILITIES</h3>
                <div id="county-facilities-list">
                    Searching for facilities...
                </div>
            </div>
        </div>
    `;

    // Filter maternal hospitals for this county
    const facilities = maternalHospitals.filter(h => h.county.toLowerCase() === props.NAME.toLowerCase());
    const listDiv = document.getElementById('county-facilities-list');

    if (facilities.length > 0) {
        listDiv.innerHTML = facilities.map(f => `
            <div class="facility-pill level-${f.level ? f.level.replace('Level ', '') : 'none'}">
                <strong>${f.name}</strong><br>
                <small>${f.level ? f.level : 'Undesignated'}</small>
            </div>
        `).join('');
    } else {
        listDiv.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No designated maternal care facilities found in this county.</p>';
    }
}

// Logic to find county by point
function findCountyByPoint(latlng) {
    let found = null;
    geojson.eachLayer(layer => {
        if (isPointInPolygon(latlng, layer)) {
            found = layer;
        }
    });
    return found;
}

function isPointInPolygon(latlng, layer) {
    // Simple wrapper for Leaflet's point-in-polygon logic
    const point = [latlng.lng, latlng.lat];
    const feature = layer.feature;
    if (feature.geometry.type === 'Polygon') {
        return polyContains(feature.geometry.coordinates[0], point);
    } else if (feature.geometry.type === 'MultiPolygon') {
        return feature.geometry.coordinates.some(poly => polyContains(poly[0], point));
    }
    return false;
}

function polyContains(poly, point) {
    let x = point[0], y = point[1];
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        let xi = poly[i][0], yi = poly[i][1];
        let xj = poly[j][0], yj = poly[j][1];
        let intersect = ((yi > y) != (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

// Utility to find county by name
function findCountyLayerByName(name) {
    if (!geojson) return null;
    let found = null;
    geojson.eachLayer(layer => {
        if (layer.feature.properties.NAME.toLowerCase() === name.toLowerCase()) {
            found = layer;
        }
    });
    return found;
}

// Data Processing
async function loadData() {
    try {
        // 1. Load GeoJSON
        const geoResponse = await fetch(GEOJSON_URL);
        const geoData = await geoResponse.json();
        const georgiaFeatures = geoData.features.filter(f => f.properties.STATE === GEORGIA_FIPS);

        geojson = L.geoJson({ type: "FeatureCollection", features: georgiaFeatures }, {
            style: style,
            onEachFeature: onEachFeature
        }).addTo(map);

        // 2. Load Data from global constants (data.js)
        allHospitals = HOSPITALS_DATA.elements;

        // 3. Load Updated ob_hospitals_with_level.csv BEFORE processing markers
        const hospitalDataResponse = await fetch('Updated ob_hospitals_with_level(ob_hospitals_with_level).csv');
        const hospitalDataText = await hospitalDataResponse.text();
        parseHospitalMetrics(hospitalDataText);

        // 4. Match and Map (now using hospital CSV data)
        processMaternalMarkers();

        // 5. Load county_data.csv for Home sidebar
        const countyDataResponse = await fetch('county_data.csv');
        const countyDataText = await countyDataResponse.text();
        parseHomeCountyData(countyDataText);

        // 7. Setup Search
        setupSearch();

    } catch (err) {
        console.error('Error loading data:', err);
    }
}

function parseHomeCountyData(text) {
    const lines = text.split('\n');
    homeCountyData = {};

    // Header format: county,pct_late_no_prenatal_care,pct_births_in_state,state,ob_beds,level,avg_distance_miles,fips,risk_factor
    // Columns: 0:county, 1:pct_late, 2:pct_births, 3:state, 4:ob_beds, 5:level, 6:avg_distance_miles, 7:fips, 8:risk_factor
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const parts = line.split(',');
        if (parts.length >= 9) {
            const county = parts[0].trim();
            homeCountyData[county] = {
                noPrenatalCare: parts[1].trim(),
                birthPct: parts[2].trim(),
                obBeds: parts[4].trim(),
                level: parts[5].trim(),
                avgDistance: parts[6].trim(),
                riskFactor: parts[8].trim()
            };
        }
    }
}

function parseHospitalMetrics(text) {
    const lines = text.split('\n');
    hospitalMetrics = {};
    maternalHospitals = []; // Populate directly from hospital CSV

    // Header: Hospital Name,county,level,Address,Number of OB Beds,Total Births
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        // Handle quoted fields (e.g., "3,023")
        const parts = line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);
        if (parts.length >= 6) {
            const name = parts[0].replace(/"/g, '').trim();
            const county = parts[1].replace(/"/g, '').trim();
            const levelRaw = parts[2].replace(/"/g, '').trim();
            const address = parts[3].replace(/"/g, '').trim();
            const obBeds = parts[4].replace(/"/g, '').trim();
            const totalBirths = parts[5].replace(/"/g, '').trim();
            
            // Map raw level numbers to level names
            const levelMap = { '1': 'Level I', '2': 'Level II', '3': 'Level III', '4': 'Level IV' };
            const level = levelMap[levelRaw] || '';
            
            const normalizedName = normalizeHospitalName(name);
            
            hospitalMetrics[normalizedName] = {
                name: name,
                county: county,
                level: level,
                address: address,
                obBeds: obBeds,
                totalBirths: totalBirths
            };
            
            // Add to maternalHospitals directly from CSV
            if (name && county) {
                maternalHospitals.push({
                    name: name,
                    county: county,
                    level: level,
                    address: address,
                    obBeds: obBeds,
                    totalBirths: totalBirths,
                    lat: null,
                    lon: null
                });
            }
        }
    }
}

function parseMaternalCSV(text) {
    const lines = text.split('\n');
    const results = [];

    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        // Handle quoted fields
        const parts = line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);
        if (parts.length >= 2) {
            const name = parts[0].replace(/"/g, '').trim();
            const county = parts[1].replace(/"/g, '').trim();
            const levelRaw = parts[2] ? parts[2].replace(/"/g, '').trim() : '';
            const levelMap = { '1': 'Level I', '2': 'Level II', '3': 'Level III', '4': 'Level IV' };
            const level = levelMap[levelRaw] || '';

            if (name && county) {
                results.push({ name, county, level, address: '' });
            }
        }
    }
    return results;
}

function formatAddress(tags) {
    if (!tags) return '';
    const housenumber = tags['addr:housenumber'] || '';
    const street = tags['addr:street'] || '';
    const city = tags['addr:city'] || '';
    const postcode = tags['addr:postcode'] || '';

    let addr = [];
    if (housenumber || street) addr.push(`${housenumber} ${street}`.trim());
    if (city) addr.push(city);
    if (postcode) addr.push(postcode);

    return addr.length > 0 ? addr.join(', ') : '';
}

function normalizeHospitalName(name) {
    if (!name) return '';
    return name.toLowerCase()
        .replace(/st\./g, 'saint')
        .replace(/st /g, 'saint ')
        .replace(/hospital/g, '')
        .replace(/healthcare/g, '')
        .replace(/medical center/g, '')
        .replace(/regional/g, '')
        .replace(/center/g, '')
        .replace(/[^a-z0-9]/g, ' ') // Replace non-alphanumeric with spaces to avoid merging words
        .split(/\s+/)
        .filter(word => word.length > 0)
        .join(' ')
        .trim();
}

function createPinIcon(color) {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="42" viewBox="0 0 36 42">
      <!-- Shadow base -->
      <ellipse cx="18" cy="39" rx="8" ry="3" fill="#c8e8e7" opacity="0.7"/>
      <!-- Pin body -->
      <path d="M18 2 C9.163 2 2 9.163 2 18 C2 28.5 18 40 18 40 C18 40 34 28.5 34 18 C34 9.163 26.837 2 18 2 Z"
            fill="${color}" stroke="#333" stroke-width="2"/>
      <!-- Inner white circle -->
      <circle cx="18" cy="17" r="9" fill="#fff8f7" stroke="#333" stroke-width="1.5"/>
      <!-- Cross horizontal -->
      <rect x="11" y="14.5" width="14" height="5" rx="2" fill="${color}" stroke="#333" stroke-width="1"/>
      <!-- Cross vertical -->
      <rect x="15.5" y="10" width="5" height="14" rx="2" fill="${color}" stroke="#333" stroke-width="1"/>
    </svg>`;
    return L.divIcon({
        html: svg,
        className: '',
        iconSize: [36, 42],
        iconAnchor: [18, 40],
        popupAnchor: [0, -40]
    });
}

function processMaternalMarkers() {
    maternalHospitals.forEach(mh => {
        const normalizedMhName = normalizeHospitalName(mh.name);

        // Find coordinates in OSM data using improved matching
        let osm = null;
        
        // First pass: Try name matching
        osm = allHospitals.find(h => {
            if (!h.tags.name) return false;
            const normalizedOsmName = normalizeHospitalName(h.tags.name);

            // Prevent empty or very short strings from matching everything
            if (normalizedOsmName.length < 4 || normalizedMhName.length < 4) return false;

            return normalizedOsmName.includes(normalizedMhName) || normalizedMhName.includes(normalizedOsmName);
        });

        // If no match, try county + city matching using address
        if (!osm && mh.address) {
            // Extract city from address (usually between street and zip)
            const addressParts = mh.address.split(',');
            const mhCity = addressParts.length > 1 ? addressParts[1].trim() : '';
            
            osm = allHospitals.find(h => {
                if (!h.tags.name) return false;
                
                const osmCity = h.tags['addr:city'] || '';
                const normalizedOsmName = normalizeHospitalName(h.tags.name);
                
                // Match if city matches and name is reasonable length
                return mhCity.toLowerCase() === osmCity.toLowerCase() && normalizedOsmName.length > 3;
            });
        }

        if (osm) {
            mh.lat = osm.center ? osm.center.lat : osm.lat;
            mh.lon = osm.center ? osm.center.lon : osm.lon;
            
            if (!mh.address) {
                mh.address = formatAddress(osm.tags);
            }

            const color = getLevelColor(mh.level);
            const marker = L.marker([mh.lat, mh.lon], {
                icon: createPinIcon(color)
            });

            marker.bindTooltip(`<strong>${mh.name}</strong><br>${mh.level}`, { direction: 'top' });

            marker.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                selectHospital(mh);
            });

            hospitalMarkers.addLayer(marker);
            console.log(`✓ Placed ${mh.name} at [${mh.lat}, ${mh.lon}]`);
        } else {
            console.warn(`⚠ No OSM location found for: ${mh.name} in ${mh.county}`);
        }
    });
}

function getLevelColor(level) {
    if (level === 'Level IV') return '#e8614f';  // Coral
    if (level === 'Level III') return '#f59e0b'; // Amber
    if (level === 'Level II') return '#0F9D9A';  // Teal
    if (level === 'Level I') return '#66D4D1';   // Light teal
    return '#a0b4b3'; // Neutral gray-teal for undesignated
}

function selectHospital(mh) {
    const updatePanel = () => updateInfoPanelWithHospital(mh);

    if (mh.lat && mh.lon) {
        const latlng = L.latLng(mh.lat, mh.lon);

        // Detailed hospital zoom
        map.setView(latlng, 15, { animate: true });

        const countyLayer = findCountyByPoint(latlng);
        if (countyLayer) {
            // Highlight county but DON'T override our detailed zoom
            selectCounty(countyLayer, countyLayer.feature.properties, true);
        }
        updatePanel();
    } else if (mh.county) {
        // Fallback: Zoom to the county level if specific hospital coordinates are missing
        const countyLayer = findCountyLayerByName(mh.county);
        if (countyLayer) {
            selectCounty(countyLayer, countyLayer.feature.properties, false);
            updatePanel();
        } else {
            updatePanel();
        }
    } else {
        updatePanel();
    }
}

function updateInfoPanelWithHospital(mh) {
    const panel = document.getElementById('info-content');
    const existingHTML = panel.innerHTML;

    // Clear previous details if any to avoid stacking multiple hospital cards
    const cleanHTML = existingHTML.split('<div class="facility-detail')[0];

    const normalizedName = normalizeHospitalName(mh.name);
    const metrics = hospitalMetrics[normalizedName] || {};
    const obBeds = metrics.obBeds || 'N/A';
    const totalBirths = metrics.totalBirths || 'N/A';

    panel.innerHTML = `
        <div class="facility-detail" style="background: white; border: 1px solid var(--accent); border-radius: 20px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: var(--shadow);">
            <h3 style="color: var(--accent); margin-bottom: 0.5rem; font-size: 1.4rem;">${mh.name}</h3>
            <p><strong>Care Level:</strong> ${mh.level || 'Undesignated'}</p>
            <p><strong>Address:</strong> ${mh.address || 'Not Available'}</p>
            <p><strong>County:</strong> ${mh.county}</p>
            <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border); display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div>
                    <span style="display: block; font-size: 0.75rem; color: var(--primary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Obstetric Beds</span>
                    <span style="font-size: 1.1rem; color: var(--text);">${obBeds}</span>
                </div>
                <div>
                    <span style="display: block; font-size: 0.75rem; color: var(--primary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Total Births</span>
                    <span style="font-size: 1.1rem; color: var(--text);">${totalBirths}</span>
                </div>
            </div>
        </div>
        ${cleanHTML}
    `;
}

function setupSearch() {
    const input = document.getElementById('hospital-search');
    const resultsDiv = document.getElementById('search-results');

    input.addEventListener('input', () => {
        const query = input.value.toLowerCase().trim();
        if (!query) {
            resultsDiv.classList.add('hidden');
            return;
        }

        const filteredHospitals = maternalHospitals.filter(h =>
            h.name.toLowerCase().includes(query) || h.county.toLowerCase().includes(query)
        ).sort((a, b) => {
            // Prioritize results that have coordinates matched
            if (a.lat && !b.lat) return -1;
            if (!a.lat && b.lat) return 1;
            return 0;
        }).slice(0, 5);

        if (filteredHospitals.length > 0) {
            resultsDiv.innerHTML = filteredHospitals.map(h => `
                <div class="search-result-item" data-id="${h.name}">
                    <span class="result-name">${h.name}</span>
                    <span class="result-meta">${h.level} • ${h.county} County</span>
                </div>
            `).join('');
            resultsDiv.classList.remove('hidden');

            document.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    const name = item.getAttribute('data-id');
                    const hospital = maternalHospitals.find(h => h.name === name);
                    if (hospital) {
                        selectHospital(hospital);
                        input.value = hospital.name;
                        resultsDiv.classList.add('hidden');
                    }
                });
            });
        } else {
            resultsDiv.innerHTML = '<div class="search-result-item">No results found</div>';
            resultsDiv.classList.remove('hidden');
        }
    });

    // Handle Enter keypress
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = input.value.toLowerCase().trim();
            const firstResult = maternalHospitals.find(h =>
                h.name.toLowerCase().includes(query) || h.county.toLowerCase().includes(query)
            );

            if (firstResult) {
                selectHospital(firstResult);
                input.value = firstResult.name;
                resultsDiv.classList.add('hidden');
            }
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#search-section')) {
            resultsDiv.classList.add('hidden');
        }
    });
}

// Tab Switching Logic
function setupTabs() {
    const navLinks = document.querySelectorAll('.nav-links li');
    const tabs = document.querySelectorAll('.tab-content');

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const tabId = link.getAttribute('data-tab');

            // Update Active Link
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            // Switch Content
            tabs.forEach(tab => {
                tab.classList.remove('active');
                if (tab.id === `${tabId}-tab`) {
                    tab.classList.add('active');
                }
            });

            // Fix Leaflet sizing if switching back to map
            if (tabId === 'home') {
                setTimeout(() => {
                    map.invalidateSize();
                }, 100);
            } else if (tabId === 'add') {
                initExpansionMap();
            } else if (tabId === 'chatbot') {
                initChatbot();
            }
        });
    });
}

// ============================
// Chatbot Functionality
// ============================

let chatbotInitialized = false;

async function initChatbot() {
    if (chatbotInitialized) return;
    chatbotInitialized = true;

    // Load suggested prompts
    try {
        const response = await fetch('/api/suggested-prompts');
        const data = await response.json();
        displaySuggestedPrompts(data.prompts);
    } catch (err) {
        console.error('Failed to load prompts:', err);
    }
    
    // Wire up input
    const sendBtn = document.getElementById('send-chat');
    const input = document.getElementById('chat-input');
    
    if (sendBtn && input) {
        sendBtn.onclick = sendMessage;
        input.onkeypress = (e) => {
            if (e.key === 'Enter') sendMessage();
        };
    }
}

function displaySuggestedPrompts(prompts) {
    const container = document.getElementById('suggested-prompts');
    if (!container) return;
    
    container.innerHTML = prompts.map(prompt => 
        `<div class="suggested-prompt" onclick="askQuestion(\`${prompt.replace(/`/g, '\\`')}\`)">${prompt}</div>`
    ).join('');
}

function askQuestion(question) {
    const input = document.getElementById('chat-input');
    if (!input) return;
    
    input.value = question;
    sendMessage();
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const messagesDiv = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-chat');
    
    if (!input || !messagesDiv) return;
    
    const message = input.value.trim();
    if (!message) return;
    
    // Disable input while processing
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
    
    // Add user message
    messagesDiv.innerHTML += `<div class="user-message"><strong>You:</strong> ${escapeHtml(message)}</div>`;
    input.value = '';
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    // Show loading
    messagesDiv.innerHTML += `<div class="bot-message" id="loading"><strong>MaternalCompass AI:</strong> Thinking...</div>`;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        const loadingEl = document.getElementById('loading');
        if (loadingEl) loadingEl.remove();
        
        if (data.success) {
            messagesDiv.innerHTML += `<div class="bot-message"><strong>MaternalCompass AI:</strong> ${escapeHtml(data.response)}</div>`;
        } else {
            messagesDiv.innerHTML += `<div class="bot-message"><strong>Error:</strong> ${escapeHtml(data.error)}</div>`;
        }
    } catch (err) {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) loadingEl.remove();
        
        messagesDiv.innerHTML += `<div class="bot-message"><strong>Error:</strong> Failed to connect to chatbot. Make sure the Flask server is running.</div>`;
        console.error('Chat error:', err);
    }
    
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    // Re-enable input
    input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

loadData();
setupTabs();

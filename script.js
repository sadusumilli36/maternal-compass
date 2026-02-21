// Georgia County Interactive Map & Maternal Care Explorer

const GEORGIA_FIPS = '13';
const GEOJSON_URL = 'https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json';

// Initialize Map
const map = L.map('map').setView([32.8381, -83.6347], 7);

// Dark Theme Tiles
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

let geojson;
let clickedLayer;
let hospitalMarkers = L.layerGroup().addTo(map);
let allHospitals = [];
let maternalHospitals = [];

// Style for counties
function style(feature) {
    return {
        fillColor: '#4f46e5',
        weight: 1,
        opacity: 1,
        color: 'rgba(255, 255, 255, 0.2)',
        fillOpacity: 0.2
    };
}

// Function to highlight a feature
function highlightFeature(layer) {
    layer.setStyle({
        weight: 2,
        color: '#818cf8',
        fillOpacity: 0.7,
        fillColor: '#6366f1'
    });
    layer.bringToFront();
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
    highlightFeature(clickedLayer);
    updateInfoPanel(props);

    if (!skipZoom) {
        map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 9 });
    }
}

function updateInfoPanel(props) {
    const panel = document.getElementById('info-content');
    panel.innerHTML = `
        <div class="county-info">
            <h2>${props.NAME} County</h2>
            <div class="info-grid">
                <div class="info-item">
                    <span class="info-label">State</span>
                    <span class="info-value">Georgia</span>
                </div>
                <div class="info-item">
                    <span class="info-label">FIPS Code</span>
                    <span class="info-value">${props.STATE}${props.COUNTY}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Type</span>
                    <span class="info-value">${props.LSAD}</span>
                </div>
            </div>
            <div class="maternal-facilities-list">
                <h3>Maternal Care Facilities</h3>
                <div id="county-facilities-list">
                    Searching for facilities in this county...
                </div>
            </div>
        </div>
    `;

    // Filter maternal hospitals for this county
    const facilities = maternalHospitals.filter(h => h.county.toLowerCase() === props.NAME.toLowerCase());
    const listDiv = document.getElementById('county-facilities-list');

    if (facilities.length > 0) {
        listDiv.innerHTML = facilities.map(f => `
            <div class="facility-pill level-${f.level.replace('Level ', '').trim()}">
                <strong>${f.name}</strong><br>
                <small>${f.level}</small>
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
        maternalHospitals = parseMaternalCSV(MATERNAL_CSV_DATA);

        // 4. Match and Map
        processMaternalMarkers();

        // 5. Setup Search
        setupSearch();

    } catch (err) {
        console.error('Error loading data:', err);
    }
}

function parseMaternalCSV(text) {
    const lines = text.split('\n');
    let currentLevel = '';
    const results = [];

    for (let line of lines) {
        line = line.trim();
        if (!line) continue;

        if (line.startsWith('Level ')) {
            currentLevel = line.split(',')[0].trim();
            continue;
        }

        if (line.startsWith('Facility Name')) continue;

        // Handle quoted addresses
        const parts = line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);
        if (parts.length >= 2) {
            results.push({
                name: parts[0].trim(),
                county: parts[1].trim(),
                address: parts[2] ? parts[2].replace(/"/g, '').trim() : '',
                level: currentLevel
            });
        }
    }
    return results;
}

function processMaternalMarkers() {
    maternalHospitals.forEach(mh => {
        // Find coordinates in OSM data
        const osm = allHospitals.find(h =>
            h.tags.name && (h.tags.name.toLowerCase().includes(mh.name.toLowerCase()) ||
                mh.name.toLowerCase().includes(h.tags.name.toLowerCase()))
        );

        if (osm) {
            mh.lat = osm.center ? osm.center.lat : osm.lat;
            mh.lon = osm.center ? osm.center.lon : osm.lon;

            const color = getLevelColor(mh.level);
            const marker = L.circleMarker([mh.lat, mh.lon], {
                radius: 8,
                fillColor: color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            });

            marker.bindTooltip(`<strong>${mh.name}</strong><br>${mh.level}`, { direction: 'top' });

            marker.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                selectHospital(mh);
            });

            hospitalMarkers.addLayer(marker);
        }
    });
}

function getLevelColor(level) {
    if (level.includes('IV')) return '#ef4444'; // Red
    if (level.includes('III')) return '#f59e0b'; // Amber
    if (level.includes('II')) return '#10b981'; // Green
    return '#3b82f6'; // Blue for Level I
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
    panel.innerHTML = `
        <div class="facility-detail glass-panel">
            <h3 style="color: var(--accent);">${mh.name}</h3>
            <p><strong>Care Level:</strong> ${mh.level}</p>
            <p><strong>Address:</strong> ${mh.address}</p>
            <p><strong>County:</strong> ${mh.county}</p>
        </div>
        ${existingHTML}
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

loadData();

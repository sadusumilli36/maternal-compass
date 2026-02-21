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
    zoomSnap: 0.1
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

        container.onclick = function () {
            map.fitBounds(georgiaBounds);
        };

        return container;
    }
});

map.addControl(new ResetControl());

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
function highlightFeature(layer) {
    layer.setStyle({
        weight: 2.5,
        color: '#e8614f',
        fillOpacity: 0.45,
        fillColor: '#0F9D9A'
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
            <h2 style="color: var(--accent); font-size: 2.2rem; margin-bottom: 1.5rem;">${props.NAME} County</h2>
            <div class="info-grid">
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600;">STATE</span>
                    <span class="info-value">Georgia</span>
                </div>
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600;">FIPS CODE</span>
                    <span class="info-value">${props.STATE}${props.COUNTY}</span>
                </div>
                <div class="info-item">
                    <span class="info-label" style="color: var(--primary); font-weight: 600;">TYPE</span>
                    <span class="info-value">${props.LSAD}</span>
                </div>
            </div>
            <div class="maternal-facilities-list">
                <h3 style="color: var(--primary); opacity: 0.8; margin-top: 2rem;">MATERNAL CARE FACILITIES</h3>
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
        // Find coordinates in OSM data
        const osm = allHospitals.find(h =>
            h.tags.name && (h.tags.name.toLowerCase().includes(mh.name.toLowerCase()) ||
                mh.name.toLowerCase().includes(h.tags.name.toLowerCase()))
        );

        if (osm) {
            mh.lat = osm.center ? osm.center.lat : osm.lat;
            mh.lon = osm.center ? osm.center.lon : osm.lon;

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

    panel.innerHTML = `
        <div class="facility-detail" style="background: white; border: 1px solid var(--accent); border-radius: 20px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: var(--shadow);">
            <h3 style="color: var(--accent); margin-bottom: 0.5rem; font-size: 1.4rem;">${mh.name}</h3>
            <p><strong>Care Level:</strong> ${mh.level || 'Undesignated'}</p>
            <p><strong>Address:</strong> ${mh.address || 'Not Available'}</p>
            <p><strong>County:</strong> ${mh.county}</p>
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
            }
        });
    });
}

loadData();
setupTabs();

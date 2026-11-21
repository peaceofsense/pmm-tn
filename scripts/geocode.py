import re
from pathlib import Path
import geopandas as gpd
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

# 1. Load the new CEV capacity dataset
csv_path = BASE_DIR / "tn_cev_capacity.csv"
df = pd.read_csv(csv_path)

# 2. Curated plant coordinates for private, new, or specific expansion plants
KNOWN_COORDS = {
    # Private / Captive Plants
    "OPG Power Generation Private Limited": (13.4116, 80.1278),  # Gummidipoondi
    "TCP Limited": (13.3850, 80.1380),                          # Gummidipoondi
    "Tulsyan NEC Limited": (13.3980, 80.1290),                  # Gummidipoondi
    # New / Under-construction Coal plants
    "UDANGUDI TPP": (8.4870, 78.0770),                          # Udangudi, Thoothukudi
    "MUTHIARA TPP": (8.9159, 78.1374),                          # Melamaruthur, Thoothukudi
    "Nagai TPP": (10.7480, 79.8450),                            # Nagapattinam
    "NORTH CHENNAI TPS STAGE 3": (13.2450, 80.3257),            # North Chennai Complex
    "TUTICORIN TPP ST-IV": (8.7635, 78.1753),                   # Tuticorin Complex
    "NEYVELI NEW TPP": (11.5950, 79.4680),                      # Neyveli New Thermal Power Station
    # Gas Plants
    "P.NALLUR CCPP": (11.0749, 79.8340),                        # Pillaiperumalnallur
    "VALUTHUR CCPP": (9.3484, 78.9235),                         # Valuthur, Ramanathapuram
    "KOVIKALPAL CCPP": (10.5415, 79.4507),                      # Kovilkalappal, Tiruvarur
    "KUTTALAM CCPP": (11.0760, 79.5700),                        # Kuttalam, Nagapattinam
    # Hydro / Nuclear specific locations
    "BHAWANI BARRAGE-II HPS": (11.3310, 77.7580),               # Bhavani Kattalai Barrage-II
    "BHAWANI BARRAGE-III HPS": (11.2428, 77.8659),              # Bhavani Kattalai Barrage-III
    "METTUR TUNNEL HPS": (11.8014, 77.8085),                    # Mettur Dam Tunnel
    "MOYAR  HPS": (11.5830, 76.7160),                           # Moyar Hydro Power Station
    "Madras APS": (12.5571, 80.1754),                           # Kalpakkam (M.A.P.P.)
    "PARSON`S VALLEY HPS": (11.3646, 76.6045),                  # Parsons Valley, Nilgiris
}

# 3. Load verified CEA coordinates from the interim database for existing power stations
cea_file = REPO_DIR / "data" / "interim" / "tamil_nadu_powerplants.csv"
cea_lookup = {}
if cea_file.exists():
    cea_df = pd.read_csv(cea_file)
    for _, row in cea_df.dropna(subset=["latitude", "longitude"]).iterrows():
        name_key = str(row["name"]).strip().upper()
        cea_lookup[name_key] = (float(row["latitude"]), float(row["longitude"]))

# Plant name normalization helper for matching
def normalize_name(name: str) -> str:
    n = name.replace("`", "'")
    n = re.sub(r"\b(TPS|TPP|HPS|CCPP|APS|GT|PROJECT|LIMITED|PVT|PRIVATE)\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\bSTAGE\s*[0-9IVX]+\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"-[0-9IVX]+(\s*EXP)?", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\(.*?\)", "", n)
    n = n.replace("ULTMATE", "ULTIMATE")
    n = n.replace("KOVIKALPAL", "KOVILKALAPPAL")
    return re.sub(r"\s+", " ", n).strip().upper()

# 4. Geocoder fallback for any unmapped entities
geolocator = Nominatim(user_agent="tn_power_geo")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)

lats = []
lons = []
matched_source = []

for raw_name in df["Name"]:
    norm = normalize_name(raw_name)
    coords = None
    source = None

    # Priority A: Curated known coordinates
    if raw_name in KNOWN_COORDS:
        coords = KNOWN_COORDS[raw_name]
        source = "Curated Plant Coordinate"

    # Priority B: Direct or partial CEA lookup
    if not coords:
        raw_upper = raw_name.upper().strip()
        # Direct exact match in CEA
        if raw_upper in cea_lookup:
            coords = cea_lookup[raw_upper]
            source = "CEA / Global Power Plant Database"
        else:
            # Fuzzy/substring match in CEA
            for cea_name, cea_coords in cea_lookup.items():
                if norm and (norm == cea_name or norm in cea_name or cea_name in norm):
                    coords = cea_coords
                    source = f"CEA Match ({cea_name})"
                    break

    # Priority C: Nominatim Geocoder fallback
    if not coords:
        query = f"{norm} Tamil Nadu, India"
        try:
            res = geocode(query)
            if res:
                coords = (res.latitude, res.longitude)
                source = f"Nominatim: {res.address}"
        except Exception as e:
            print(f"Geocoding error for {raw_name}: {e}")

    if coords:
        lats.append(coords[0])
        lons.append(coords[1])
        matched_source.append(source)
    else:
        lats.append(None)
        lons.append(None)
        matched_source.append(None)

df["lat"] = lats
df["lon"] = lons
df["matched_source"] = matched_source

# Save rows that failed
unmatched = df[df["lat"].isna()]
unmatched.to_csv(BASE_DIR / "unmatched.csv", index=False)

# Build point geometry and save spatial layers
ok = df.dropna(subset=["lat", "lon"]).copy()
gdf = gpd.GeoDataFrame(
    ok,
    geometry=gpd.points_from_xy(ok["lon"], ok["lat"]),
    crs="EPSG:4326",
)
gdf.to_file(BASE_DIR / "tn_plants.gpkg", layer="plants", driver="GPKG")
gdf.to_file(BASE_DIR / "tn_plants.geojson", driver="GeoJSON")
gdf.to_csv(BASE_DIR / "tn_plants.csv", index=False)

print(f"Successfully matched {len(ok)} of {len(df)} plants from tn_cev_capacity.csv")
if len(unmatched) > 0:
    print(f"Unmatched plants saved to unmatched.csv: {len(unmatched)}")

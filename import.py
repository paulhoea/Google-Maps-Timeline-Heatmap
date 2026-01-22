#################
##### SETUP #####
#################

# %% Setup 
# Libraries
import json
import folium
import datetime
import shapefile
import shapely
import pandas as pd
import geopandas as gpd
import numpy as np
from folium.plugins import HeatMap
from sklearn.neighbors import BallTree
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
#import matplotlib.cm as cm


# Filepaths
import_file = "/home/paul/Documents/Timeline/Timeline.json"
export_file = "/home/paul/Documents/Timeline/Table.csv"
steps_file = "/home/paul/Documents/Timeline/StepsAppDataExport/activity-export-hourly.csv"
district_file = "/home/paul/Documents/Timeline/Shapefiles/WFS GetFeature (SHP)-17.zip"

# Filters
day_start = 6
day_end = 22
start_date = '2025-01-01'
end_date = '2025-12-31'
# start_date = '2025-10-02T00:00:00' # LINZ
# end_date = '2025-10-02T23:59:59'
# start_date = '2025-10-08T00:00:00'
# end_date = '2025-10-08T23:59:59'
steps_treshold = 12000


# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

# the semantic segments encode relevant parts of the data, the steps are imported from a separate app
df = pd.json_normalize(data["semanticSegments"])
steps_df = pd.read_csv(steps_file, delimiter=";")
steps_df = steps_df.iloc[1:]

districts_shp = shp = shapefile.Reader(district_file, encoding = "ISO8859-1")
districts_gdf = gpd.read_file(district_file)

# %% Handle date filtering
# prepare for safe addition
df['startTimeTimezoneUtcOffsetMinutes'] = df['startTimeTimezoneUtcOffsetMinutes'].fillna(0)
df['endTimeTimezoneUtcOffsetMinutes'] = df['endTimeTimezoneUtcOffsetMinutes'].fillna(0)

# covert to date
df['startTime'] = pd.to_datetime(df['startTime'],utc=True)
df['endTime'] = pd.to_datetime(df['endTime'],utc=True)
df["date"] = df["startTime"].dt.date

# incorporate the timezone offset
df['startTime'] = df['startTime'] + pd.to_timedelta(df['startTimeTimezoneUtcOffsetMinutes'], unit='m')
df['endTime'] = df['endTime'] + pd.to_timedelta(df['endTimeTimezoneUtcOffsetMinutes'], unit='m')

# filter date
mask = (df['startTime'] >= start_date) & (df['startTime'] <= end_date)
filtered_df = df.loc[mask]

# %% Filter to keep only daytime hours
filtered_df = filtered_df[
    (filtered_df['startTime'].dt.hour >= day_start) & (filtered_df['startTime'].dt.hour < day_end) &
    (filtered_df['endTime'].dt.hour >= day_start) & (filtered_df['endTime'].dt.hour < day_end)
]
# %% Filter for Walking (and NaN, which are unassigned raw location information to be processed manually) segments
filtered_df['activity.topCandidate.type'].unique() # there would be other interesting modes, like skiing
filtered_df['activity.topCandidate.type'].value_counts(dropna=False) # many paths do not get assigned an activity, hence have to keep NaNs in the analysis

# Keep only WALKING and NaN (unassigned) segments
filtered_df = filtered_df[
    (filtered_df["activity.topCandidate.type"] == "WALKING")
    | (filtered_df["activity.topCandidate.type"].isna()) # included to keep data with timelinePath, which does not get assigned an activity type
]

# %% Optional: raw data export
# filtered_df['startTime'] = filtered_df['startTime'].dt.tz_localize(None)
# filtered_df['endTime'] = filtered_df['endTime'].dt.tz_localize(None)
# filtered_df.to_excel('/home/paul/test.xlsx', sheet_name='sheet1', index=False)

# %% Keep only travel (i.e. remove any visits)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.


###################################
### RELEVANT DAY IDENTIFICATION ###
###################################

# %%
steps_df["date_utc"] = pd.to_datetime(steps_df["date"],utc=True)
steps_df["time"] = steps_df["date_utc"].dt.hour
steps_df["date"] = steps_df["date_utc"].dt.date
steps_df["steps"] = pd.to_numeric(steps_df["steps"])

steps_df = steps_df[(steps_df["date_utc"] >= start_date) & (steps_df["date_utc"] <= end_date)]
steps_df = steps_df[(steps_df["time"] >= day_start) & (steps_df["time"] <= day_end)]


steps_df = steps_df.groupby("date")["steps"].sum().reset_index(name="steps")

# Preview whether the steps cutoff is chosen appropriately
plt.hist(steps_df["steps"], bins=range(min(steps_df["steps"]), max(steps_df["steps"]) + 2000, 2000))
plt.axvline(steps_treshold, color='k', linestyle='dashed', linewidth=1)
plt.show() 

# keep only relevant, as defined by steps threshold
steps_df["relevant"] = steps_df["steps"] > steps_treshold
steps_df.drop(columns = ["steps"], axis = 1, inplace = True)

filtered_df = filtered_df.merge(steps_df)

filtered_df = filtered_df[filtered_df["relevant"] == True] # for further processing
steps_df = steps_df[steps_df["relevant"] == True] # to tune the heuristic


##################
### PROCESSING ###
##################

# %% drop (TODO:) obsoltete and empty columns
filtered_df = filtered_df.dropna(axis='columns', how='all')

# %% timeline_df processed separately, into timelinePoints (df) for visualisation, and timelinePoints_separate (list) for (TODO) forthcoming testing
timeline_df = filtered_df[~filtered_df["timelinePath"].isna()]
timeline_df = timeline_df.dropna(axis='columns', how='all')

timelinePoints = []

for json_string in timeline_df['timelinePath']:
    timelinePoints.append(pd.json_normalize(json_string)) # more detailed format (list of dfs) for a later test
    
for item in timelinePoints:
    item["timelineLat"] = item["point"].str.split('°, ').str[0].str.replace('°', '').astype(float)
    item["timelineLon"] = item["point"].str.split('°, ').str[1].str.replace('°', '').astype(float)
    item["time"] = pd.to_datetime(item["time"],utc=True)
    item["date"] = item["time"].dt.date
    item = item.drop(columns = ["point"], axis=1, inplace=True)

points_df = pd.concat(timelinePoints)

# %% remove timelinePath parts from segement df
filtered_df = filtered_df[filtered_df["timelinePath"].isna()]

# %% Split latLng string into separate lat and lng columns
filtered_df[['startLat', 'startLon']] = filtered_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
filtered_df[['endLat', 'endLon']] = filtered_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# %% Heuristic: drop timelinePoints data if they are solitary, implying fast travel (e.g. public transport) being registered

# Convert to radians
points_df[['timelineRadLat', 'timelineRadLon']] = np.radians(points_df[['timelineLat', 'timelineLon']].values)
max_distance_km=1.0
    
# Build tree
tree = BallTree(points_df[['timelineRadLat', 'timelineRadLon']], metric='haversine')

# Find points to keep
keep_mask = np.ones(len(points_df), dtype=bool)

for i in range(len(keep_mask)):
    if not keep_mask[i]:
        continue
    # Find k=2 nearest neighbors (itself + 1 other)
    distances, indices = tree.query([points_df[['timelineRadLat', 'timelineRadLon']].iloc[i].values], k=2)
    # Check distance to nearest neighbor (index 1, since index 0 is itself)
    if len(distances[0]) > 1 and distances[0][1] > max_distance_km/6371.0:
        keep_mask[i] = False

points_df = points_df[keep_mask].reset_index(drop=True)


# %% Heuristic: remove certain areas (TODO: extend to a bespoke district filter)

# filtered_df = filtered_df.query('not (startLat >= 48.205372 & startLat <= 48.216725 & startLon >= 16.337250 & startLon <= 16.362453)')
# points_df = points_df.query('not (timelineLat >= 48.205372 & timelineLat <= 48.216725 & timelineLon >= 16.337250 & timelineLon <= 16.362453)')

points_gdf = gpd.GeoDataFrame(
    points_df,
    geometry=gpd.points_from_xy(points_df['timelineLon'], points_df['timelineLat']),
    crs='EPSG:4326'  # WGS84 - standard lat/lon
)

# Reproject points to match the shapefile's CRS
points_gdf = points_gdf.to_crs(districts_gdf.crs)

# Spatial join to find which district each point is in
result = gpd.sjoin(points_gdf, districts_gdf, how='left', predicate='within')

# for i in range(0, len(districts_shp.shapes())):
#     boundary = districts_shp.shapes()[i] # get a boundary polygon
#     for item in points_df.iterrows():
#         print(item[["timelineLat", "timelineLon"]])
#         if Point(item[["timelineLat", "timelineLon"]]).within(shape(boundary)): # make a point and see if it's in the polygon
#             item.loc[i, "district"] = districts_shp.records()[i][8] # Postleitzahl, e.g. 1100

# for item in points_df.iterrows():
#         print(item[["timelineLat", "timelineLon"]])

##################
#### ANALYSIS ####
##################

# %% count left and right turns
for item in timelinePoints:
    for i in range(2, len(item)):
        # Get the three consecutive points
        lat1, lon1 = item.loc[i-2, 'timelineLat'], item.loc[i-2, 'timelineLon']
        lat2, lon2 = item.loc[i-1, 'timelineLat'], item.loc[i-1, 'timelineLon']
        lat3, lon3 = item.loc[i, 'timelineLat'], item.loc[i, 'timelineLon']
        
        # Calculate the two vectors
        dlat1 = lat2 - lat1
        dlon1 = lon2 - lon1
        dlat2 = lat3 - lat2
        dlon2 = lon3 - lon2
        
        # Calculate cross product
        cross_product = dlat1 * dlon2 - dlon1 * dlat2
        
        # Classify the turn
        threshold = 1e-6 # this is arbitrary and can be done with other values, but this only affects what degree of movment gets counted as a turn, not turn ratios
        if cross_product > threshold:
            item.loc[i, 'turn'] = 'left'
        elif cross_product < -threshold:
            item.loc[i, 'turn'] = 'right'
        else:
            item.loc[i, 'turn'] = 'straight'

pd.concat(timelinePoints)["turn"].value_counts()


#################
#### RESULTS ####
#################
# %% Display result on map

# drop non-Vienna coordinates
filtered_df = filtered_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLon >= 16.136967 & startLon <= 16.627111')
points_df = points_df.query('timelineLat >= 48.092441 & timelineLat <= 48.349715 & timelineLon >= 16.136967 & timelineLon <= 16.627111')


# Calculate the center point for the map
center_lat = (filtered_df['startLat'].mean() + filtered_df['endLat'].mean()) / 2
center_lng = (filtered_df['startLon'].mean() + filtered_df['endLon'].mean()) / 2

# Create a map centered on your data
m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

# Add lines for each segement
for idx, row in filtered_df.iterrows():
    folium.PolyLine(
        locations=[
            [row['startLat'], row['startLon']], 
            [row['endLat'], row['endLon']]
        ],
        color='blue',
        weight=2,
        opacity=0.6
    ).add_to(m)

# assign colours to each day
min_date = points_df['date'].min()
max_date = points_df['date'].max()
days_from_min = (points_df['date'] - min_date).apply(lambda x: x.days)
max_days = (max_date - min_date).days

if max_days > 0:
    normalized = days_from_min / max_days
else:
    normalized = np.zeros(len(points_df))

# Use a colormap (hsv, rainbow, or jet are good for hue progression)
cmap = plt.get_cmap('hsv')  # or 'rainbow', 'jet', 'turbo'
points_df['colour'] = normalized.apply(lambda x: mcolors.to_hex(cmap(x)))


# add dots for each point
for idx, row in points_df.iterrows():
    folium.CircleMarker(
        location=[row['timelineLat'], row['timelineLon']],
        radius=3,
        color=row["colour"],
        fill=True,
        fillColor='red'
    ).add_to(m)

# Save and display
m.save('/home/paul/routes_map.html')
# m  # If in Jupyter, this will display inline

# Heatmap preview

h = folium.Map(location=[center_lat, center_lng], zoom_start=12)

HeatMap(points_df[["timelineLat", "timelineLon"]]).add_to(h)

h.save('/home/paul/heat_map.html')
# %%
